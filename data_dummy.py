"""
data_dummy.py
Dunia simulasi: anggota konsorsium, lulusan, verifier, dan kredensial DUMMY
(ijazah, transkrip, sertifikat kompetensi). Semua nama dan nomor fiktif.
"""
import time

from kredensial_sim import (Actor, AuditLog, Clock, Key, Network, Verifier, Wallet,
                            anchor_payload, build_credential, governance_tx)

class World:
    def __init__(self):
        self.clock = Clock()
        # Anggota genesis: empat penerbit sekaligus validator, satu pengamat (regulator).
        self.ucn = Actor("Universitas Contoh Nusantara", ["ISSUER", "VALIDATOR"])
        self.ict = Actor("Institut Contoh Teknologi", ["ISSUER", "VALIDATOR"])
        self.pcm = Actor("Politeknik Contoh Mandiri", ["ISSUER", "VALIDATOR"])
        self.lspc = Actor("Lembaga Sertifikasi Profesi Contoh", ["ISSUER", "VALIDATOR"])
        self.opc = Actor("Otoritas Pendidikan Contoh", ["OBSERVER"])
        self.ucb = Actor("Universitas Contoh Baru", ["ISSUER"])       # calon anggota baru
        self.validators = [self.ucn, self.ict, self.pcm, self.lspc]
        self.net = Network(self.clock, [self.ucn, self.ict, self.pcm, self.lspc, self.opc])
        self.audit = AuditLog()
        self.alya = Wallet("Alya Contoh", "DUMMY-0001")
        self.bagas = Wallet("Bagas Contoh", "DUMMY-0002")
        self.citra = Wallet("Citra Contoh", "DUMMY-0003")
        self.employer = Verifier("PT Contoh Rekrut", self.net, self.clock, self.audit)
        self.campus = Verifier("Universitas Contoh Lanjutan", self.net, self.clock, self.audit)
        self._n = 0
        self.catalog = {}          # nama -> cred_id

    # penerbitan
    def issue(self, issuer, wallet, ctype, claims, valid_days=None, name=None):
        self._n += 1
        cred_id = "urn:cred:dummy:%04d" % self._n
        now = self.clock.now()
        exp = now + valid_days * 86400 if valid_days else None
        cred, salts = build_credential(issuer, wallet.did, wallet.key.pub, ctype, claims,
                                       now, exp, cred_id)
        ok, why = self.net.submit(issuer.tx("ANCHOR_CREDENTIAL", anchor_payload(cred), self.clock))
        if not ok:
            raise RuntimeError("penjangkaran ditolak: " + why)
        wallet.store(cred, claims, salts)
        if name:
            self.catalog[name] = cred_id
        return cred_id

    def set_status(self, issuer, cred_id, status):
        return self.net.submit(issuer.tx("SET_STATUS", {"cred_id": cred_id, "status": status},
                                         self.clock))

    # verifikasi
    def check(self, verifier, wallet, cred_id, reveal):
        pres = wallet.present(cred_id, reveal, verifier.challenge())
        return verifier.verify(pres), pres

    def populate(self):
        """Terbitkan 7 kredensial dummy: ijazah, transkrip, sertifikat."""
        self.issue(self.ucn, self.alya, "Ijazah", {
            "nama": "Alya Contoh", "nim": "DUMMY-0001", "program_studi": "S1 Informatika",
            "gelar": "S.Kom.", "tanggal_lulus": "2026-08-20",
            "nomor_ijazah": "IJZ-DUMMY-0001", "status_kelulusan": "LULUS"},
            name="ijazah_alya")
        self.issue(self.ucn, self.alya, "Transkrip", {
            "nama": "Alya Contoh", "nim": "DUMMY-0001", "ipk": 3.72, "total_sks": 144,
            "mata_kuliah": [{"kode": "IF101", "nama": "Algoritma", "nilai": "A"},
                            {"kode": "IF305", "nama": "Blockchain", "nilai": "A"},
                            {"kode": "IF310", "nama": "Basis Data", "nilai": "B+"}],
            "tanggal_terbit": "2026-08-25"}, name="transkrip_alya")
        self.issue(self.lspc, self.alya, "SertifikatKompetensi", {
            "nama": "Alya Contoh", "skema": "Analis Data (dummy)",
            "nomor_sertifikat": "SK-DUMMY-0001", "hasil": "KOMPETEN"},
            valid_days=365, name="sertifikat_alya")
        self.issue(self.ict, self.bagas, "Ijazah", {
            "nama": "Bagas Contoh", "nim": "DUMMY-0002", "program_studi": "S1 Teknik Informatika",
            "gelar": "S.T.", "tanggal_lulus": "2026-07-30",
            "nomor_ijazah": "IJZ-DUMMY-0002", "status_kelulusan": "LULUS"},
            name="ijazah_bagas")
        self.issue(self.ict, self.bagas, "Transkrip", {
            "nama": "Bagas Contoh", "nim": "DUMMY-0002", "ipk": 3.40, "total_sks": 146,
            "mata_kuliah": [{"kode": "TI101", "nama": "Kalkulus", "nilai": "B+"},
                            {"kode": "TI404", "nama": "Keamanan Siber", "nilai": "A-"}],
            "tanggal_terbit": "2026-08-02"}, name="transkrip_bagas")
        self.issue(self.pcm, self.citra, "Ijazah", {
            "nama": "Citra Contoh", "nim": "DUMMY-0003", "program_studi": "D3 Manajemen Informatika",
            "gelar": "A.Md.Kom.", "tanggal_lulus": "2026-09-05",
            "nomor_ijazah": "IJZ-DUMMY-0003", "status_kelulusan": "LULUS"},
            name="ijazah_citra")
        self.issue(self.lspc, self.citra, "SertifikatKompetensi", {
            "nama": "Citra Contoh", "skema": "Administrator Jaringan (dummy)",
            "nomor_sertifikat": "SK-DUMMY-0002", "hasil": "KOMPETEN"},
            valid_days=730, name="sertifikat_citra")
        return self

    # tata kelola
    def gov(self, proposer, action, fields, voters):
        return self.net.submit(governance_tx(proposer, action, fields, voters, self.clock))

# benchmark
def benchmark(n=300, batch=50):
    """Ukur kecepatan simulasi (satu proses, di memori). Bukan tolok ukur jaringan nyata."""
    w = World()
    items = []
    for i in range(n):
        wal = Wallet("Dummy %d" % i, "DUMMY-B%04d" % i)
        claims = {"nama": "Dummy %d" % i, "nim": "DUMMY-B%04d" % i, "gelar": "S.Kom.",
                  "status_kelulusan": "LULUS"}
        cred, salts = build_credential(w.ucn, wal.did, wal.key.pub, "Ijazah", claims,
                                       w.clock.now(), None, "urn:cred:bench:%05d" % i)
        wal.store(cred, claims, salts)
        items.append((wal, cred))
    txs = [w.ucn.tx("ANCHOR_CREDENTIAL", anchor_payload(c), w.clock) for _, c in items]
    t0 = time.perf_counter()
    for i in range(0, n, batch):
        res = w.net.submit_many(txs[i:i + batch])
        assert all(ok for ok, _ in res), res
    t_issue = time.perf_counter() - t0
    lat = []
    for wal, cred in items:
        t1 = time.perf_counter()
        r, _ = w.check(w.employer, wal, cred["id"], ["status_kelulusan"])
        lat.append((time.perf_counter() - t1) * 1000)
        assert r["ok"], r
    lat.sort()
    return {"n": n, "batch": batch, "issue_tps": n / t_issue,
            "verify_mean_ms": sum(lat) / n, "verify_p95_ms": lat[int(0.95 * n) - 1],
            "verify_max_ms": lat[-1], "blok": w.net.height(), "node": len(w.net.nodes)}
