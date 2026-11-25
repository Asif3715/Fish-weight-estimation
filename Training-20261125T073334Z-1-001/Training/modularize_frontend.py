from pathlib import Path
root=Path(r'C:\Users\AFAN\Downloads\FYP\Data Pipeline\frontend\src')
s=(root/'main.tsx').read_text(encoding='utf-8-sig')
def write(name,text):
 p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8')
types=s[s.index('type Camera='):s.index('async function api')]
write('types/index.ts',types.replace('type ','export type '))
api=s[s.index('async function api'):s.index('function Icon')]
write('lib/api.ts',api.replace('async function api','export async function api'))
icon=s[s.index('function Icon'):s.index('function Pill')]
write('components/ui/Icon.tsx',"import type {ReactNode} from 'react';\n"+icon.replace('function Icon','export function Icon',1))
pill=s[s.index('function Pill'):s.index('const nav:')]
write('components/ui/Pill.tsx',"import type {ReactNode} from 'react';\n"+pill.replace('function Pill','export function Pill',1))
tail=s[s.index('function CheckRow'):s.index("createRoot(")]
check=tail[:tail.index('function RunItem')]
run=tail[tail.index('function RunItem'):]
write('features/overview/CheckRow.tsx',"import {Icon} from '../../components/ui/Icon';\n"+check.replace('function CheckRow','export function CheckRow',1))
write('features/recordings/RunItem.tsx',"import type {Run} from '../../types';\nimport {Icon} from '../../components/ui/Icon';\nimport {Pill} from '../../components/ui/Pill';\n"+run.replace('function RunItem','export function RunItem',1))
state=s[s.index(" const [page,setPage]"):s.index(' return <div className="app-shell">')]
state=state.replace(" const addButton=<button className=\"button primary\" onClick={newCamera} disabled={!!data.active}><Icon name=\"plus\" size={17}/>Add camera</button>;",'')
# UI rendering stays in components, not in the state provider.
names='page,setPage,health,data,drive,cameras,notice,setNotice,busy,offline,mode,setMode,note,setNote,folder,setFolder,editor,setEditor,showSecret,setShowSecret,filter,setFilter,confirmStop,setConfirmStop,action,newCamera,saveCamera,enabled,pending,uploaded,ready,go'
write('app/WorkspaceProvider.tsx',"""import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import type {Camera,Collection,Health,Drive,Page} from '../types';
import {api} from '../lib/api';

function useWorkspaceController(){
"""+state+'\n return {'+names+'''};
}
type Workspace = ReturnType<typeof useWorkspaceController>;
const WorkspaceContext = createContext<Workspace|null>(null);
export function WorkspaceProvider({children}:{children:ReactNode}){
 const workspace = useWorkspaceController();
 return <WorkspaceContext.Provider value={workspace}>{children}</WorkspaceContext.Provider>;
}
export function useWorkspace(){
 const workspace=useContext(WorkspaceContext);
 if(!workspace)throw new Error('WorkspaceProvider is required');
 return workspace;
}
''')
common="""import {useWorkspace} from '../../app/WorkspaceProvider';
import {Icon} from '../../components/ui/Icon';
import {Pill} from '../../components/ui/Pill';
import {api} from '../../lib/api';
import {AddCameraButton} from '../cameras/AddCameraButton';
import {CheckRow} from '../overview/CheckRow';
import {RunItem} from '../recordings/RunItem';
"""
write('features/cameras/AddCameraButton.tsx',"""import {useWorkspace} from '../../app/WorkspaceProvider';
import {Icon} from '../../components/ui/Icon';
export function AddCameraButton(){
 const {newCamera,data}=useWorkspace();
 return <button className="button primary" onClick={newCamera} disabled={!!data.active}><Icon name="plus" size={17}/>Add camera</button>;
}
""")
pages=[('Overview','overview','OverviewPage'),('Cameras','cameras','CamerasPage'),('Experiments','experiments','ExperimentsPage'),('Recordings','recordings','RecordingsPage'),('Storage & Drive','drive','DrivePage')]
for i,(label,folder,component) in enumerate(pages):
 start=s.index(" {page==='"+label+"'&&")
 end=s.index(" {page==='"+pages[i+1][0]+"'&&",start) if i+1<len(pages) else s.index(' <footer className="page-footer">',start)
 body=s[start:end].strip()
 body=body[body.index('&&')+2:]
 assert body.endswith('}')
 body=body[:-1].replace('{addButton}','{<AddCameraButton/>}')
 write(f'features/{folder}/{component}.tsx',common+'\nexport function '+component+'(){\n const {'+names+'}=useWorkspace();\n return ('+body+');\n}\n')
layout=s[s.index(' return <div className="app-shell">'):s.index(" {page==='Overview'&&")]
layout=layout.replace(' return <div className="app-shell">',' return <div className="app-shell">',1).replace('?addButton:', '?<AddCameraButton/>:')
constants=s[s.index('const nav:'):s.index('function App()')]
footer=s[s.index(' <footer className="page-footer">'):s.index(' {editor&&')]
write('components/layout/AppLayout.tsx',"import type {ReactNode} from 'react';\nimport type {Page} from '../../types';\n"+common.replace("'../../components/ui/", "'../ui/").replace("'../cameras/", "'../../features/cameras/").replace("'../overview/", "'../../features/overview/").replace("'../recordings/", "'../../features/recordings/")+constants+'\nexport function AppLayout({children}:{children:ReactNode}){\n const {'+names+'}=useWorkspace();\n'+layout+'{children}\n'+footer+'</div>;\n}\n')
# Dialogs are owned by their features.
editor=s[s.index(' {editor&&'):s.index(' {confirmStop&&')].strip()[len('{editor&&'):]
assert editor.endswith('}');editor=editor[:-1]
write('features/cameras/CameraDialog.tsx',common+'\nexport function CameraDialog(){\n const {'+names+'}=useWorkspace();\n if(!editor)return null;\n return ('+editor+');\n}\n')
stop=s[s.index(' {confirmStop&&'):s.index('\n </div>;')].strip()[len('{confirmStop&&'):]
assert stop.endswith('}');stop=stop[:-1]
write('features/recordings/StopRecordingDialog.tsx',common+'\nexport function StopRecordingDialog(){\n const {'+names+'}=useWorkspace();\n if(!confirmStop)return null;\n return ('+stop+');\n}\n')
imports='\n'.join(f"import {{{comp}}} from '../features/{folder}/{comp}';" for _,folder,comp in pages)
write('app/App.tsx',"""import {WorkspaceProvider,useWorkspace} from './WorkspaceProvider';
import {AppLayout} from '../components/layout/AppLayout';
import {CameraDialog} from '../features/cameras/CameraDialog';
import {StopRecordingDialog} from '../features/recordings/StopRecordingDialog';
"""+imports+"""
function WorkspacePages(){
 const {page}=useWorkspace();
 const pages={Overview:<OverviewPage/>,Cameras:<CamerasPage/>,Experiments:<ExperimentsPage/>,Recordings:<RecordingsPage/>,'Storage & Drive':<DrivePage/>};
 return <><AppLayout>{pages[page]}</AppLayout><CameraDialog/><StopRecordingDialog/></>;
}
export function App(){return <WorkspaceProvider><WorkspacePages/></WorkspaceProvider>}
""")
write('main.tsx',"import {createRoot} from 'react-dom/client';\nimport {App} from './app/App';\nimport './styles/index.css';\n\ncreateRoot(document.getElementById('root')!).render(<App/>);\n")
# Separate global tokens, layout, shared controls and feature styles without changing cascade order.
css=(root/'styles.css').read_text(encoding='utf-8-sig')
markers=['.app-shell{','.collection-bar{','.panel{','.pill{','.experiment-layout{','.modal-backdrop{','@media(min-width:1600px)']
positions=[0]+[css.index(m) for m in markers]+[len(css)]
style_names=['tokens-and-base','layout','overview','panels','devices','features','dialogs','responsive']
for name,a,b in zip(style_names,positions,positions[1:]):write(f'styles/{name}.css',css[a:b]+'\n')
write('styles/index.css','\n'.join(f"@import './{name}.css';" for name in style_names)+'\n')
print('Frontend extracted into app, feature, shared UI, API, types and stylesheet modules.')
