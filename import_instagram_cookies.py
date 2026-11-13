"""Import a user-exported Netscape cookie file; never read browser databases."""
import argparse
from http.cookiejar import MozillaCookieJar
from pathlib import Path
import os

BASE = Path(__file__).resolve().parent

def instagram_cookies(path):
    jar = MozillaCookieJar(str(path))
    jar.load(ignore_discard=True, ignore_expires=True)
    values = {}
    for cookie in jar:
        # Netscape exporters commonly use 0 for browser-session cookies.
        if cookie.expires not in (None, 0) and cookie.is_expired():
            continue
        domain = cookie.domain.lstrip('.').lower()
        if domain == 'instagram.com' or domain.endswith('.instagram.com'):
            if cookie.value:
                values[cookie.name] = cookie.value
    if not all(values.get(name) for name in ('sessionid', 'csrftoken', 'ds_user_id')):
        raise ValueError('缺少有效 Instagram 登录 Cookie；请确认浏览器已登录，再导出当前网站的 Netscape 格式文件。')
    return values

def import_session(cookie_path, username, output, check_api="graphql"):
    import instaloader
    values = instagram_cookies(cookie_path)
    loader = instaloader.Instaloader(quiet=True, max_connection_attempts=1, request_timeout=30)
    try:
        loader.load_session(username, values)
        if check_api == 'current-user':
            data = loader.context.get_iphone_json('api/v1/accounts/current_user/', params={'edit': 'true'})
            user = data.get('user') or {}
            actual = user.get('username')
            if str(user.get('pk')) != str(values['ds_user_id']):
                raise ValueError('账号接口未确认会话所属账号；未保存会话。')
        else:
            actual = loader.test_login()
        if not actual:
            raise ValueError('登录检查未能完成，并不能据此认定 Cookies 失效。若上方出现 feedback_required，请停止重试，在 Edge 检查账号是否可正常浏览、有无安全验证提示。')
        if actual.casefold() != username.casefold():
            raise ValueError('导出文件中的账号与命令指定的用户名不同；未保存会话。')
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.session.tmp')
        try:
            loader.context.username = actual
            loader.save_session_to_file(str(temporary))
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        loader.close()

def main():
    parser = argparse.ArgumentParser(description='导入手动导出的 Instagram Cookies')
    parser.add_argument('--username', required=True)
    parser.add_argument('--cookies', type=Path, default=BASE/'local-data'/'secrets'/'cookies.txt')
    parser.add_argument('--check-api', choices=['graphql', 'current-user'], default='graphql')
    args = parser.parse_args()
    output = BASE/'local-data'/'secrets'/'instagram.session'
    try:
        import_session(args.cookies, args.username, output, args.check_api)
    except FileNotFoundError:
        print('未找到 cookies.txt，请先将导出文件保存到 local-data/secrets/cookies.txt。')
        return 1
    except ValueError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        # Do not echo HTTP URLs, cookie values, or server checkpoint parameters.
        print('导入失败：'+type(exc).__name__+'。请确认文件为 Netscape 格式、网络可用且浏览器已完成登录验证。')
        return 1
    print('登录验证成功，已保存：'+str(output))
    print('请确认 .env 中 IG_USERNAME 与本次用户名一致，然后重启本地界面。')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())



