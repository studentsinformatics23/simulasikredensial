"""
kredensial_sim.py
Simulasi DUMMY sistem verifikasi kredensial akademik berbasis jaringan konsorsium.

PENTING
- Semua data, nama, nomor, dan kunci di sini FIKTIF. Tidak ada koneksi ke jaringan
  blockchain, layanan, atau lembaga yang nyata. Semuanya berjalan di memori.
- Konsensus DISEDERHANAKAN (pemimpin bergilir + persetujuan mayoritas, mirip pola
  tahan-crash). Ini bukan implementasi Raft atau BFT yang sebenarnya.
- Kunci dibuat deterministik dari nama agar simulasi dapat diulang. Jangan dipakai
  di tempat lain.
"""
import hashlib
import json
import secrets
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

# ---------------------------------------------------------------- utilitas
def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")

def sha(data):
    return hashlib.sha256(data).hexdigest()

def sha_obj(obj):
    return sha(canon(obj))

def slug(text):
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in text).split())

class Clock:
    """Jam simulasi (detik epoch UTC) agar uji kedaluwarsa bersifat deterministik."""
    def __init__(self, start="2026-10-15T00:00:00+00:00"):
        self.t = int(datetime.fromisoformat(start).timestamp())
    def now(self):
        return self.t
    def advance(self, days=0, seconds=0):
        self.t += days * 86400 + seconds
    @staticmethod
    def iso(ts):
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")

class Key:
    """Pasangan kunci Ed25519 DUMMY (seed deterministik dari label)."""
    def __init__(self, label):
        seed = hashlib.sha256(b"dummy-seed:" + label.encode()).digest()
        self._sk = Ed25519PrivateKey.from_private_bytes(seed)
        self.pub = self._sk.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw).hex()
    def sign(self, msg):
        return self._sk.sign(msg).hex()

def verify_sig(pub_hex, msg, sig_hex):
    try:
        Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub_hex)).verify(
            bytes.fromhex(sig_hex), msg)
        return True
    except (InvalidSignature, ValueError):
        return False

# ---------------------------------------------------------------- aktor & transaksi
class Actor:
    """Anggota jaringan (penerbit, validator, atau pengamat) dengan kunci dummy."""
    def __init__(self, name, roles, label=None):
        self.name = name
        self.roles = sorted(roles)
        self.label = label or name
        self.key = Key(self.label)
        self.did = "did:dummy:" + slug(name)
        self.nonce = 0

    def tx(self, ttype, payload, clock):
        self.nonce += 1
        body = {"type": ttype, "payload": payload, "sender": self.did,
                "nonce": self.nonce, "ts": clock.now()}
        return {**body, "sig": self.key.sign(canon(body))}

def tx_body(tx):
    return {k: tx[k] for k in ("type", "payload", "sender", "nonce", "ts")}

GOV_ACTIONS = ("ADD_MEMBER", "DEACTIVATE_MEMBER", "FLAG_KEY_COMPROMISED", "REPLACE_KEY")
_prop_counter = [0]

def governance_tx(proposer, action, fields, voters, clock):
    """Bangun transaksi tata kelola: proposal + suara bertanda tangan para validator."""
    _prop_counter[0] += 1
    proposal = {"id": "prop-%04d" % _prop_counter[0], "action": action, **fields}
    votes = {v.did: v.key.sign(canon(proposal)) for v in voters}
    return proposer.tx(action, {"proposal": proposal, "votes": votes}, clock)

# ---------------------------------------------------------------- state ledger
class State:
    """World state: anggota, jangkar kredensial, nonce. Deterministik."""
    def __init__(self, genesis_members):
        self.members = {}
        for m in genesis_members:
            self.members[m["did"]] = {
                "name": m["name"], "roles": list(m["roles"]), "status": "ACTIVE",
                "keys": [{"pub": m["pub"], "from_height": 0, "compromised_from": None}]}
        self.creds = {}
        self.nonces = {}
        self.used_proposals = set()

    def validators(self):
        return [d for d, m in self.members.items()
                if "VALIDATOR" in m["roles"] and m["status"] == "ACTIVE"]

    def quorum_gov(self):
        return (2 * len(self.validators())) // 3 + 1

    def check_tx(self, tx, height, pend=None):
        """Pemeriksaan murni (tidak mengubah state). Mengembalikan (ok, alasan)."""
        s = tx.get("sender")
        m = self.members.get(s)
        if m is None:
            return False, "PENGIRIM_TIDAK_TERDAFTAR"
        if m["status"] != "ACTIVE":
            return False, "ANGGOTA_NONAKTIF"
        key = m["keys"][-1]
        if key.get("compromised_from") is not None:
            return False, "KUNCI_DIKOMPROMIKAN"
        if not verify_sig(key["pub"], canon(tx_body(tx)), tx.get("sig", "")):
            return False, "TANDA_TANGAN_TX_TIDAK_VALID"
        last = max(self.nonces.get(s, 0), (pend or {}).get(s, 0))
        if tx["nonce"] <= last:
            return False, "NONCE_ULANG"
        if not (set(m["roles"]) & {"ISSUER", "VALIDATOR"}):
            return False, "HANYA_BACA"
        t, p = tx["type"], tx["payload"]
        if t == "ANCHOR_CREDENTIAL":
            if "ISSUER" not in m["roles"]:
                return False, "BUKAN_PENERBIT"
            if p["issuer"] != s:
                return False, "PENERBIT_TIDAK_SESUAI"
            if p["cred_id"] in self.creds:
                return False, "CRED_ID_SUDAH_ADA"
            return True, "OK"
        if t == "SET_STATUS":
            c = self.creds.get(p["cred_id"])
            if c is None:
                return False, "CRED_TIDAK_ADA"
            if c["issuer"] != s:
                return False, "BUKAN_PENERBIT_KREDENSIAL"
            allowed = {"ACTIVE": {"SUSPENDED", "REVOKED"},
                       "SUSPENDED": {"ACTIVE", "REVOKED"}, "REVOKED": set()}
            if p["status"] not in allowed[c["status"]]:
                return False, "TRANSISI_STATUS_DITOLAK"
            return True, "OK"
        if t == "ROTATE_KEY":
            new_pub = p.get("new_pub", "")
            if len(new_pub) != 64:
                return False, "KUNCI_BARU_TIDAK_VALID"
            return True, "OK"
        if t in GOV_ACTIONS:
            if "VALIDATOR" not in m["roles"]:
                return False, "BUKAN_VALIDATOR"
            return self._check_governance(t, p)
        return False, "TIPE_TX_TIDAK_DIKENAL"

    def _check_governance(self, t, p):
        prop, votes = p["proposal"], p["votes"]
        if prop.get("action") != t:
            return False, "PROPOSAL_TIDAK_SESUAI"
        if prop["id"] in self.used_proposals:
            return False, "PROPOSAL_SUDAH_DIPAKAI"
        vals = set(self.validators())
        good = sum(1 for d, sg in votes.items()
                   if d in vals and verify_sig(self.members[d]["keys"][-1]["pub"],
                                               canon(prop), sg))
        if good < self.quorum_gov():
            return False, "KUORUM_TIDAK_TERPENUHI"
        if t == "ADD_MEMBER" and prop["member"]["did"] in self.members:
            return False, "ANGGOTA_SUDAH_ADA"
        if t != "ADD_MEMBER" and prop["target"] not in self.members:
            return False, "TARGET_TIDAK_ADA"
        return True, "OK"

    def apply_tx(self, tx, height):
        ok, why = self.check_tx(tx, height)
        if not ok:
            raise RuntimeError("Divergensi state: %s" % why)
        s, t, p = tx["sender"], tx["type"], tx["payload"]
        self.nonces[s] = tx["nonce"]
        if t == "ANCHOR_CREDENTIAL":
            self.creds[p["cred_id"]] = {
                "issuer": s, "type": p["type"], "cred_hash": p["cred_hash"],
                "root": p["root"], "expires_at": p["expires_at"], "status": "ACTIVE",
                "anchored_height": height,
                "anchor_key": self.members[s]["keys"][-1]["pub"]}
        elif t == "SET_STATUS":
            self.creds[p["cred_id"]]["status"] = p["status"]
        elif t == "ROTATE_KEY":
            self.members[s]["keys"][-1]["until_height"] = height
            self.members[s]["keys"].append(
                {"pub": p["new_pub"], "from_height": height, "compromised_from": None})
        else:  # tata kelola
            prop = p["proposal"]
            self.used_proposals.add(prop["id"])
            if t == "ADD_MEMBER":
                mem = prop["member"]
                self.members[mem["did"]] = {
                    "name": mem["name"], "roles": list(mem["roles"]), "status": "ACTIVE",
                    "keys": [{"pub": mem["pub"], "from_height": height,
                              "compromised_from": None}]}
            elif t == "DEACTIVATE_MEMBER":
                self.members[prop["target"]]["status"] = "INACTIVE"
            elif t == "FLAG_KEY_COMPROMISED":
                self.members[prop["target"]]["keys"][-1]["compromised_from"] = prop["from_height"]
            elif t == "REPLACE_KEY":
                keys = self.members[prop["target"]]["keys"]
                keys[-1]["until_height"] = height
                keys.append({"pub": prop["new_pub"], "from_height": height,
                             "compromised_from": None})

# ---------------------------------------------------------------- blok & node
def tx_root(txs):
    return sha_obj([sha_obj(t) for t in txs])

def block_hash(b):
    return sha_obj({"height": b["height"], "prev_hash": b["prev_hash"], "ts": b["ts"],
                    "tx_root": b["tx_root"], "proposer": b["proposer"],
                    "cfg": b.get("cfg")})

class Node:
    def __init__(self, actor, genesis):
        self.actor = actor
        self.name = actor.name
        self.online = True
        self.chain = [copy_obj(genesis)]
        self.state = State(genesis["cfg"]["members"])

    @property
    def is_validator(self):
        return "VALIDATOR" in self.actor.roles

    def head(self):
        return self.chain[-1]

    def height(self):
        return self.chain[-1]["height"]

    def vote(self, block):
        """Validasi struktural blok oleh validator (setuju atau tidak)."""
        if not (self.online and self.is_validator):
            return False
        h = self.head()
        return (block["height"] == h["height"] + 1 and block["prev_hash"] == h["hash"]
                and tx_root(block["txs"]) == block["tx_root"]
                and block_hash(block) == block["hash"])

    def apply(self, block):
        for tx in block["txs"]:
            self.state.apply_tx(tx, block["height"])
        self.chain.append(copy_obj(block))

    def verify_chain(self):
        for i, b in enumerate(self.chain):
            if b["height"] != i:
                return False, "tinggi blok %d tidak berurutan" % i
            if tx_root(b["txs"]) != b["tx_root"] or block_hash(b) != b["hash"]:
                return False, "blok %d tidak konsisten dengan hash-nya" % i
            if i > 0 and b["prev_hash"] != self.chain[i - 1]["hash"]:
                return False, "tautan prev_hash blok %d putus" % i
        return True, "OK"

def copy_obj(o):
    return json.loads(json.dumps(o))

class Network:
    """Jaringan konsorsium simulasi: validator + pengamat, konsensus mayoritas."""
    def __init__(self, clock, members):
        self.clock = clock
        cfg = {"members": [{"did": a.did, "name": a.name, "roles": a.roles, "pub": a.key.pub}
                           for a in members]}
        genesis = {"height": 0, "prev_hash": "0" * 64, "ts": clock.now(), "txs": [],
                   "proposer": "genesis", "cfg": cfg, "tx_root": tx_root([])}
        genesis["hash"] = block_hash(genesis)
        self.nodes = {a.did: Node(a, genesis) for a in members
                      if set(a.roles) & {"VALIDATOR", "OBSERVER"}}
        self.total_validators = sum(1 for n in self.nodes.values() if n.is_validator)

    # -- akses baca (gateway): memakai node yang sedang daring
    def read_node(self):
        for n in self.nodes.values():
            if n.online:
                return n
        raise RuntimeError("tidak ada node daring")

    def height(self):
        return max(n.height() for n in self.nodes.values() if n.online)

    def query_anchor(self, cred_id):
        c = self.read_node().state.creds.get(cred_id)
        return copy_obj(c) if c else None

    def query_member(self, did):
        m = self.read_node().state.members.get(did)
        return copy_obj(m) if m else None

    # -- konsensus
    def quorum(self):
        return self.total_validators // 2 + 1

    def _leader(self):
        online = [n for n in self.nodes.values() if n.is_validator and n.online]
        if not online:
            return None
        return online[self.height() % len(online)]

    def submit(self, tx):
        return self.submit_many([tx])[0]

    def submit_many(self, txs):
        leader = self._leader()
        if leader is None:
            return [(False, "TIDAK_ADA_PEMIMPIN")] * len(txs)
        accepted, results, pend = [], [], {}
        for tx in txs:
            ok, why = leader.state.check_tx(tx, leader.height() + 1, pend)
            results.append((ok, why))
            if ok:
                accepted.append(tx)
                pend[tx["sender"]] = tx["nonce"]
        if not accepted:
            return results
        h = leader.head()
        block = {"height": h["height"] + 1, "prev_hash": h["hash"], "ts": self.clock.now(),
                 "txs": accepted, "proposer": leader.actor.did, "tx_root": tx_root(accepted)}
        block["hash"] = block_hash(block)
        votes = sum(1 for n in self.nodes.values() if n.vote(block))
        if votes < self.quorum():
            return [(False, "KUORUM_KONSENSUS_GAGAL") if r[0] else r for r in results]
        for n in self.nodes.values():
            if n.online:
                n.apply(block)
        return results

    def recover(self, did):
        """Node kembali daring dan menyusul blok yang tertinggal dari peer."""
        node = self.nodes[did]
        peer = max((n for n in self.nodes.values() if n.online and n is not node),
                   key=lambda n: n.height())
        for b in peer.chain[node.height() + 1:]:
            node.apply(b)
        node.online = True

    def consistency_report(self):
        rep = {}
        for n in self.nodes.values():
            ok, msg = n.verify_chain()
            rep[n.name] = {"online": n.online, "tinggi": n.height(),
                           "head": n.head()["hash"][:12], "rantai_valid": ok, "catatan": msg}
        heads = {r["head"] for r in rep.values() if r["online"]}
        return rep, len(heads) == 1 and all(r["rantai_valid"] for r in rep.values())

# ---------------------------------------------------------------- kredensial (off-chain)
def commit_claim(salt, name, value):
    return sha(("%s|%s|" % (salt, name)).encode() + canon(value))

def build_credential(issuer, holder_did, holder_pub, ctype, claims,
                     issued_at, expires_at, cred_id):
    """Buat kredensial mirip-VC (dummy). Nilai atribut TIDAK ada di dalamnya,
    hanya komitmen (hash bergaram) per atribut."""
    salts = {k: secrets.token_hex(8) for k in claims}
    commitments = {k: commit_claim(salts[k], k, v) for k, v in claims.items()}
    root = sha_obj(sorted(commitments.items()))
    cred = {
        "@context": ["contoh-konteks/kredensial-akademik-dummy/v1"],
        "id": cred_id,
        "type": ["VerifiableCredential(dummy)", ctype],
        "issuer": issuer.did,
        "issuanceDate": Clock.iso(issued_at),
        "issued_at": issued_at,
        "expires_at": expires_at,
        "credentialSubject": {"id": holder_did, "holderKey": holder_pub,
                              "commitments": commitments, "root": root},
    }
    cred["proof"] = {"type": "Ed25519-dummy", "verificationMethod": issuer.key.pub,
                     "signature": issuer.key.sign(canon(cred))}
    return cred, salts

def anchor_payload(cred):
    """Isi yang dicatat di ledger: hanya hash dan metadata, tanpa data pribadi/pemegang."""
    return {"cred_id": cred["id"], "type": cred["type"][1],
            "cred_hash": sha_obj(cred), "root": cred["credentialSubject"]["root"],
            "expires_at": cred["expires_at"], "issuer": cred["issuer"]}

class Wallet:
    """Dompet lulusan (off-chain): menyimpan kredensial, atribut, garam, dan kunci."""
    def __init__(self, name, nim):
        self.name, self.nim = name, nim
        self.key = Key("holder:" + name)
        self.did = "did:dummy:holder-" + slug(name)
        self.items = {}

    def store(self, cred, claims, salts):
        self.items[cred["id"]] = {"cred": cred, "claims": claims, "salts": salts}

    def new_key(self, label):
        self.key = Key(label)

    def present(self, cred_id, reveal, challenge):
        it = self.items[cred_id]
        disclosed = {k: {"value": it["claims"][k], "salt": it["salts"][k]} for k in reveal}
        body = {"cred_id": cred_id, "nonce": challenge["nonce"],
                "verifier": challenge["verifier"], "reveal": sorted(reveal)}
        return {"credential": it["cred"], "disclosed": disclosed,
                "holder_proof": {"body": body, "signature": self.key.sign(canon(body))}}

# ---------------------------------------------------------------- audit log
class AuditLog:
    """Log audit berantai-hash (append-only). Tidak menyimpan nilai atribut."""
    def __init__(self):
        self.entries = []

    def append(self, event):
        prev = self.entries[-1]["hash"] if self.entries else "0" * 64
        e = {"seq": len(self.entries), "event": event, "prev": prev}
        e["hash"] = sha_obj({"seq": e["seq"], "event": event, "prev": prev})
        self.entries.append(e)

    def verify(self):
        prev = "0" * 64
        for i, e in enumerate(self.entries):
            if e["seq"] != i or e["prev"] != prev:
                return False
            if sha_obj({"seq": e["seq"], "event": e["event"], "prev": e["prev"]}) != e["hash"]:
                return False
            prev = e["hash"]
        return True

# ---------------------------------------------------------------- verifier
class Verifier:
    def __init__(self, name, network, clock, audit):
        self.name, self.net, self.clock, self.audit = name, network, clock, audit
        self.did = "did:dummy:verifier-" + slug(name)
        self.pending = {}

    def challenge(self, ttl=300):
        nonce = secrets.token_hex(16)
        self.pending[nonce] = self.clock.now() + ttl
        return {"nonce": nonce, "verifier": self.did}

    def verify(self, pres):
        res = self._verify(pres)
        cid = pres.get("credential", {}).get("id", "?") if isinstance(pres, dict) else "?"
        self.audit.append({"verifier": self.did, "cred_id": cid, "hasil": res["code"],
                           "ts": self.clock.now()})
        return res

    @staticmethod
    def _res(code, detail="", revealed=None):
        return {"ok": code == "OK", "code": code, "detail": detail, "revealed": revealed or {}}

    def _verify(self, pres):
        try:
            cred, disclosed = pres["credential"], pres["disclosed"]
            hp = pres["holder_proof"]
            body, hsig = hp["body"], hp["signature"]
            nonce = body["nonce"]
        except (KeyError, TypeError):
            return self._res("FORMAT_TIDAK_VALID")
        exp = self.pending.pop(nonce, None)           # nonce sekali pakai
        if exp is None or self.clock.now() > exp:
            return self._res("REPLAY_ATAU_NONCE_TIDAK_DIKENAL")
        if body.get("verifier") != self.did:
            return self._res("PRESENTASI_UNTUK_VERIFIER_LAIN")
        anchor = self.net.query_anchor(cred.get("id"))
        if anchor is None:
            return self._res("TIDAK_ADA_DI_LEDGER")
        if sha_obj(cred) != anchor["cred_hash"]:
            return self._res("HASH_TIDAK_COCOK", "isi kredensial berbeda dari yang dijangkarkan")
        unsigned = {k: v for k, v in cred.items() if k != "proof"}
        if not verify_sig(anchor["anchor_key"], canon(unsigned), cred["proof"]["signature"]):
            return self._res("TANDA_TANGAN_PENERBIT_TIDAK_VALID")
        issuer = self.net.query_member(anchor["issuer"])
        if issuer is None:
            return self._res("PENERBIT_TIDAK_DIKENAL")
        for k in issuer["keys"]:
            if k["pub"] == anchor["anchor_key"] and k["compromised_from"] is not None \
               and anchor["anchored_height"] >= k["compromised_from"]:
                return self._res("KUNCI_PENERBIT_DIKOMPROMIKAN",
                                 "dijangkarkan pada/ setelah tinggi %d" % k["compromised_from"])
        if anchor["status"] == "REVOKED":
            return self._res("DICABUT")
        if anchor["status"] == "SUSPENDED":
            return self._res("DITANGGUHKAN")
        if anchor["expires_at"] is not None and self.clock.now() > anchor["expires_at"]:
            return self._res("KEDALUWARSA")
        commits = cred["credentialSubject"]["commitments"]
        revealed = {}
        for k, d in disclosed.items():
            if k not in commits or commit_claim(d["salt"], k, d["value"]) != commits[k]:
                return self._res("ATRIBUT_TIDAK_COCOK_DENGAN_KOMITMEN", k)
            revealed[k] = d["value"]
        if body.get("cred_id") != cred["id"] or sorted(disclosed) != body.get("reveal"):
            return self._res("BUKTI_PEMEGANG_TIDAK_COCOK")
        if not verify_sig(cred["credentialSubject"]["holderKey"], canon(body), hsig):
            return self._res("BUKTI_PEMEGANG_TIDAK_VALID")
        note = "penerbit nonaktif" if issuer["status"] != "ACTIVE" else ""
        return self._res("OK", note, revealed)
