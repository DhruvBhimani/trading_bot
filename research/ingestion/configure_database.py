"""Save a hosted connection locally without displaying the password or URL."""
import getpass
import os
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def main():
    path=Path(__file__).resolve().parents[2]/'.env'
    url=getpass.getpass('Paste the DIRECT PostgreSQL connection URL (hidden): ').strip()
    try:
        parsed=urlsplit(url)
        if parsed.scheme not in ('postgres','postgresql') or not parsed.hostname or not parsed.username or not parsed.path.strip('/') or '\n' in url or '\r' in url:
            raise ValueError()
    except ValueError:
        raise SystemExit('Invalid PostgreSQL URL. Nothing saved.') from None
    # Quotes protect # characters from dotenv parsing; escape literal quote/backslash.
    value="'"+url.replace('\\','\\\\').replace("'","\\'")+"'"
    lines=path.read_text().splitlines() if path.exists() else []
    lines=[line for line in lines if not line.strip().startswith(('DATABASE_URL=', 'export DATABASE_URL='))]
    lines.append('DATABASE_URL='+value)
    fd,temporary=tempfile.mkstemp(prefix='.env.setup-',dir=str(path.parent))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'w') as output:
            output.write('\n'.join(lines)+'\n')
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    print('Saved DATABASE_URL to the ignored .env file. Connection has not been tested yet.')


if __name__=='__main__':main()
