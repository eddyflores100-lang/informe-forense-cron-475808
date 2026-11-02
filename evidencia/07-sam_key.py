#!/usr/bin/env python3
"""sam_key.py — CLI de la bóveda OpenSAM Key Vault.

Lee/actualiza el mismo archivo cifrado que el sitio (secrets/opensam-vault.enc).
La clave jamás se imprime en logs; solo con los comandos explícitos get/env.

Uso:
  python3 scripts/sam_key.py status            # estado + días restantes
  python3 scripts/sam_key.py get SAM_GOV_API_KEY
  python3 scripts/sam_key.py env               # imprime `export VAR="..."` listas para pegar
  python3 scripts/sam_key.py set SAM_GOV_API_KEY <valor>   # o sin valor para prompt oculto
"""
import sys, os, json, getpass, datetime

VAULT = '/home/z/my-project/secrets/opensam-vault.enc'
MASTER = '/home/z/my-project/secrets/.opensam-vault.master'
SLOTS = ('SAM_GOV_API_KEY', 'OPENSAM_ACCESS_TOKEN')
TTL_DAYS = 90

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    print('Falta dependencia: pip install cryptography', file=sys.stderr)
    sys.exit(2)


def _keys():
    key = bytes.fromhex(open(MASTER).read().strip())
    raw = open(VAULT, 'rb').read()
    if raw[:4] != b'OSV1':
        raise SystemExit('formato de bóveda desconocido')
    iv, tag, ct = raw[4:16], raw[16:32], raw[32:]
    return json.loads(AESGCM(key).decrypt(iv, ct + tag, None))


def _save(data):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    import secrets as _s
    key = bytes.fromhex(open(MASTER).read().strip())
    iv = _s.token_bytes(12)
    pt = json.dumps(data, ensure_ascii=False).encode()
    blob = AESGCM(key).encrypt(iv, pt, None)   # ct||tag
    ct, tag = blob[:-16], blob[-16:]           # formato Node: OSV1|iv|tag|ct
    tmp = VAULT + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(b'OSV1' + iv + tag + ct)
    os.replace(tmp, VAULT)


def _mask(v):
    return v[:4] + '••••••' + v[-4:] if len(v) > 10 else '••••••'


def _days_left(entry):
    entered = datetime.datetime.fromisoformat(entry['enteredAt'].replace('Z', '+00:00'))
    if entered.tzinfo is None:
        entered = entered.replace(tzinfo=datetime.timezone.utc)
    expires = entered + datetime.timedelta(days=TTL_DAYS)
    return (expires - datetime.datetime.now(datetime.timezone.utc)).days


def cmd_status():
    d = _keys()
    for slot in SLOTS:
        e = d['slots'].get(slot)
        if not e or not e.get('value'):
            print(f'{slot:22} VACÍA')
            continue
        dl = _days_left(e)
        state = 'OK' if dl > 30 else ('ROTA PRONTO' if dl > 0 else 'EXPIRADA')
        exp = (datetime.datetime.fromisoformat(e['enteredAt']) + datetime.timedelta(days=TTL_DAYS)).strftime('%d-%b-%Y')
        print(f'{slot:22} {_mask(e["value"])}  vence {exp}  ({dl} días)  [{state}]')


def cmd_get(slot):
    if slot not in SLOTS:
        print(f'slot inválido; usa: {", ".join(SLOTS)}', file=sys.stderr); sys.exit(2)
    d = _keys()
    e = d['slots'].get(slot)
    if not e or not e.get('value'):
        print(f'{slot} está vacía', file=sys.stderr); sys.exit(1)
    print(e['value'])


def cmd_env():
    d = _keys()
    out = []
    for slot in SLOTS:
        e = d['slots'].get(slot)
        if e and e.get('value'):
            out.append(f'export {slot}="{e["value"]}"')
    if not out:
        print('no hay claves guardadas', file=sys.stderr); sys.exit(1)
    print('\n'.join(out))


def cmd_set(slot, value=None):
    if slot not in SLOTS:
        print(f'slot inválido; usa: {", ".join(SLOTS)}', file=sys.stderr); sys.exit(2)
    if not value:
        value = getpass.getpass(f'valor para {slot} (entrada oculta): ')
    value = value.strip()
    if not value or (' ' in value):
        print('valor vacío o con espacios', file=sys.stderr); sys.exit(2)
    if slot == 'OPENSAM_ACCESS_TOKEN' and len(value) < 32:
        print('el token debe tener 32+ caracteres', file=sys.stderr); sys.exit(2)
    if slot == 'SAM_GOV_API_KEY' and len(value) < 20:
        print('la api key debe tener 20+ caracteres', file=sys.stderr); sys.exit(2)
    d = _keys()
    prev = d['slots'].get(slot)
    hist = prev.get('history', []) if prev else []
    if prev and prev.get('value'):
        hist = hist + [{'masked': _mask(prev['value']), 'setAt': prev['enteredAt'], 'removedAt': datetime.datetime.now(datetime.timezone.utc).isoformat()}]
    d.setdefault('slots', {})[slot] = {'value': value, 'enteredAt': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'history': hist}
    _save(d)
    print(f'{slot} guardada (cifrada). Reloj de 90 días reiniciado.')


def main():
    args = sys.argv[1:]
    if not args or args[0] not in ('status', 'get', 'env', 'set'):
        print(__doc__); sys.exit(2)
    c = args[0]
    if c == 'status': cmd_status()
    elif c == 'env': cmd_env()
    elif c == 'get' and len(args) >= 2: cmd_get(args[1])
    elif c == 'set' and len(args) >= 2: cmd_set(args[1], args[2] if len(args) > 2 else None)
    else: print(__doc__); sys.exit(2)


if __name__ == '__main__':
    main()

# ===================================================================
# NOTA FORENSE (2026-11-02): este archivo se incluye en el repo de
# auditoria como evidencia del diseño de la bóveda. Copia LECTURA de
# scripts/sam_key.py (mtime 2026-10-26 21:50:40 UTC). No contiene
# secretos: lee la master key de secrets/.opensam-vault.master y el
# vault cifrado de secrets/opensam-vault.enc (ninguno incluido aquí).
# El comando 'status' solo imprime IDs enmascarados y fechas.
# ===================================================================
