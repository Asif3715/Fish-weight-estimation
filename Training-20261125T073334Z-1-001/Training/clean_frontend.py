from pathlib import Path
import re
r=Path(r'C:\Users\AFAN\Downloads\FYP\Data Pipeline\frontend\src')
for p in list((r/'features').rglob('*.tsx'))+list((r/'components/layout').rglob('*.tsx')):
 s=p.read_text(encoding='utf-8')
 match=re.search(r' const \{([^}]+)\}=useWorkspace\(\);',s)
 if match:
  body=s[match.end():]
  used=[n for n in match.group(1).split(',') if re.search(r'\b'+n+r'\b',body)]
  s=s[:match.start()]+' const {'+','.join(used)+'}=useWorkspace();'+s[match.end():]
 for match in list(re.finditer(r'^import \{([^}]+)\} from ([^;]+);\n',s,re.M))[::-1]:
  remaining=s[:match.start()]+s[match.end():]
  used=[n for n in match.group(1).split(',') if re.search(r'\b'+n.strip()+r'\b',remaining)]
  replacement='import {'+','.join(used)+'} from '+match.group(2)+';\n' if used else ''
  s=s[:match.start()]+replacement+s[match.end():]
 p.write_text(s,encoding='utf-8')
# Keep CSS cascade identical to the source, partitioning only at ordered boundaries.
css=(r/'styles.css').read_text(encoding='utf-8-sig')
markers=['.app-shell{','.collection-bar{','.pill{','.experiment-layout{','.modal-backdrop{','@media(min-width:1600px)']
positions=[0]+[css.index(m) for m in markers]+[len(css)]
assert positions==sorted(positions)
names=['tokens-and-base','layout','overview','components','features','dialogs','responsive']
for name,a,b in zip(names,positions,positions[1:]):(r/'styles'/f'{name}.css').write_text(css[a:b]+'\n',encoding='utf-8')
(r/'styles/index.css').write_text(''.join(f"@import './{n}.css';\n" for n in names),encoding='utf-8')
# Polling belongs in a dedicated hook; callers receive a small state API.
p=r/'app/WorkspaceProvider.tsx';s=p.read_text()
start=s.index('function useWorkspaceController()')
end=s.index('type Workspace =')
hook=s[start:end].replace('function useWorkspaceController','export function useWorkspaceController',1)
hooks=r/'hooks';hooks.mkdir(exist_ok=True)
(hooks/'useWorkspaceController.ts').write_text("import {useEffect,useState} from 'react';\nimport type {Camera,Collection,Health,Drive,Page} from '../types';\nimport {api} from '../lib/api';\n"+hook,encoding='utf-8')
p.write_text("import {createContext,useContext,type ReactNode} from 'react';\nimport {useWorkspaceController} from '../hooks/useWorkspaceController';\n"+s[end:],encoding='utf-8')
print('Removed unused imports and bindings; extracted controller hook; preserved CSS order.')
