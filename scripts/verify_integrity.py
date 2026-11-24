"""Check SHA256SUMS; permit generated outputs but reject modified listed files."""
import hashlib
import json
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]


def main():
    issues=[];count=0
    for line in (ROOT/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.startswith('#'):continue
        expected,name=line.split('  ',1)
        relative=PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or ':' in name or '\\' in name:
            raise ValueError('Unsafe manifest member')
        path=ROOT.joinpath(*relative.parts)
        for component in [path,*path.parents]:
            if component==ROOT.parent:break
            if component.is_symlink() or component.is_junction():raise ValueError('Manifest links rejected')
        count+=1
        if not path.is_file():issues.append({'path':name,'reason':'MISSING'});continue
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        if actual!=expected:issues.append({'path':name,'reason':'HASH_MISMATCH'})
    report={'status':'FAIL' if issues else 'PASS','checked_files':count,'issues':issues,
            'scope':'SHA256SUMS excludes itself; the outer ZIP SHA256 authenticates its delivered bytes'}
    print(json.dumps(report))
    return 1 if issues else 0


if __name__=='__main__':
    raise SystemExit(main())
