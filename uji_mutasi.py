"""
uji_mutasi.py
Uji mutasi manual: menyisipkan satu kesalahan ke salinan kode, lalu memastikan suite uji
gagal (mutan "terdeteksi"). Jika ada mutan lolos, berarti ada celah pada uji.
"""
import os, re, shutil, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
MUTAN = [
 ("M1 nonce tidak sekali pakai", "exp = self.pending.pop(nonce, None)", "exp = self.pending.get(nonce, None)"),
 ("M2 status DICABUT diabaikan", 'if anchor["status"] == "REVOKED":', 'if False:'),
 ("M3 kedaluwarsa diabaikan", 'if anchor["expires_at"] is not None and self.clock.now() > anchor["expires_at"]:', 'if False:'),
 ("M4 bukti pemegang tidak diperiksa", 'if not verify_sig(cred["credentialSubject"]["holderKey"], canon(body), hsig):', 'if False:'),
 ("M5 kuorum tata kelola dilonggarkan", "return (2 * len(self.validators())) // 3 + 1", "return 1"),
 ("M6 otorisasi penerbit kredensial dilonggarkan", 'if c["issuer"] != s:', 'if False:'),
 ("M7 pemeriksaan hash blok dimatikan", 'if tx_root(b["txs"]) != b["tx_root"] or block_hash(b) != b["hash"]:', 'if False:'),
 ("M8 kompromi kunci diabaikan", 'and anchor["anchored_height"] >= k["compromised_from"]:', 'and False:'),
 ("M9 komitmen atribut tidak dicek", 'if k not in commits or commit_claim(d["salt"], k, d["value"]) != commits[k]:', 'if k not in commits:'),
 ("M10 kuorum konsensus dilonggarkan", "return self.total_validators // 2 + 1", "return 1"),
]

def main():
    src = open(os.path.join(BASE, "kredensial_sim.py"), encoding="utf8").read()
    terdeteksi = 0
    for nama, lama, baru in MUTAN:
        assert src.count(lama) == 1, nama
        with tempfile.TemporaryDirectory() as d:
            for f in ("data_dummy.py", "test_kredensial_sim.py"):
                shutil.copy(os.path.join(BASE, f), d)
            open(os.path.join(d, "kredensial_sim.py"), "w", encoding="utf8").write(src.replace(lama, baru))
            p = subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=d,
                               capture_output=True, text=True)
        gagal = sorted(set(re.findall(r"test_(t\d+)", p.stderr)))
        ids = ", ".join(("T-" + g[1:]) for g in gagal) or "-"
        ok = p.returncode != 0
        terdeteksi += ok
        print("%-48s %s oleh %s" % (nama, "TERDETEKSI" if ok else "LOLOS (celah uji)", ids))
    print("\nRingkasan: %d dari %d mutan terdeteksi." % (terdeteksi, len(MUTAN)))

if __name__ == "__main__":
    main()
