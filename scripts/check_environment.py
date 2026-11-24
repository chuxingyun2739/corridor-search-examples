"""Verify the recorded graph runtime without accepting a legacy psutil pin."""
import importlib.metadata
import json
import platform
import struct
import sys
from pathlib import Path


def main():
    actual = {'python':platform.python_version(), 'system':platform.system(), 'bits':struct.calcsize('P')*8,
              'networkx':importlib.metadata.version('networkx'), 'psutil':importlib.metadata.version('psutil'),
              'virtual_environment':sys.prefix != sys.base_prefix}
    expected={'python':'3.13.3','system':'Windows','bits':64,'networkx':'3.5','psutil':'7.1.2','virtual_environment':True}
    checks=[{'field':key,'expected':value,'actual':actual[key],'status':'PASS' if actual[key]==value else 'FAIL'} for key,value in expected.items()]
    result={'status':'PASS' if all(c['status']=='PASS' for c in checks) else 'FAIL','checks':checks,
            'scope':'Validated R3 runtime; legacy psutil 7.0.0 runner is not included or claimed tested'}
    output=Path(__file__).resolve().parents[1]/'outputs/environment.json'
    output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
