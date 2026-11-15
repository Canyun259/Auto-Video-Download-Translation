import ast,json,sqlite3,tempfile,unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest
from database_setup import ensure_schema,ManagedConnection
from video_metadata import save

class LibraryUITests(unittest.TestCase):
    def test_pagination_lazy_details_and_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            data=Path(directory)
            path=data/'library.sqlite'
            with sqlite3.connect(path,factory=ManagedConnection) as c:
                ensure_schema(c)
                for i in range(30):
                    save(c,str(i),'https://example.com/'+str(i),{'title':'Video '+str(i),'uploader':'Alice'})
                save(c,'done','https://example.com/done',{'title':'Completed video'})
                c.execute("UPDATE videos SET state='done' WHERE id='done'")
            tree=ast.parse(Path(__file__).with_name('local_ui.py').read_text(encoding='utf-8'))
            functions=[]
            for n in tree.body:
                if isinstance(n,ast.FunctionDef) and n.name in {'db','filter_publishers','show_library'}:
                    n.decorator_list=[];functions.append(ast.unparse(n))
            script='import streamlit as st\nimport sqlite3,hashlib,json\nfrom pathlib import Path\nfrom urllib.parse import urlparse\nfrom output_paths import output_folder\nDATA=Path('+repr(str(data))+')\n'+'\n'.join(functions)+'\nshow_library()\n'
            page=AppTest.from_string(script).run(timeout=30)
            self.assertFalse(page.exception)
            self.assertEqual(len(page.subheader),12)
            self.assertEqual(len(page.radio),1) # Task options are not eagerly rendered.
            page.number_input(key='library-page-待选择').set_value(3).run()
            self.assertEqual(len(page.subheader),6)
            page.button(key='delete-5').click().run()
            self.assertFalse(page.exception)
            with sqlite3.connect(path,factory=ManagedConnection) as c: self.assertEqual(c.execute("SELECT hidden FROM videos WHERE id='5'").fetchone()[0],1)
            page.checkbox(key='delete-select-4').check().run()
            page.button(key='delete-page').click().run()
            with sqlite3.connect(path,factory=ManagedConnection) as c: self.assertEqual(c.execute("SELECT hidden FROM videos WHERE id='4'").fetchone()[0],1)
            page.radio(key='library-section').set_value('已完成').run()
            self.assertEqual(len(page.subheader),1)
            self.assertEqual(len(page.get('video')),0)
            artifact=data/'result.mp4';artifact.write_bytes(b'keep output')
            page.button(key='delete-done').click().run()
            self.assertFalse(page.exception)
            self.assertEqual(artifact.read_bytes(),b'keep output')
            self.assertEqual(len(page.subheader),0)

if __name__=='__main__': unittest.main()
