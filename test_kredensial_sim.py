"""
Uji simulasi kredensial akademik (data DUMMY). Jalankan: python -m unittest -v
Setiap uji diberi kode T-xx yang dirujuk pada laporan.
"""
import copy
import json
import unittest

from kredensial_sim import (Actor, Key, Wallet, anchor_payload, build_credential, canon)
from data_dummy import World, benchmark

IJAZAH_PUBLIK = ["program_studi", "gelar", "status_kelulusan"]

def mk():
    return World().populate()

class Fungsional(unittest.TestCase):
    def test_t01_terbit_dan_verifikasi_semua_jenis(self):
        """T-01 Semua kredensial dummy (ijazah, transkrip, sertifikat) terbit dan lolos verifikasi"""
        w = mk()
        for nama, cid in w.catalog.items():
            wal = {"alya": w.alya, "bagas": w.bagas, "citra": w.citra}[nama.split("_")[1]]
            r, _ = w.check(w.employer, wal, cid, [])
            self.assertTrue(r["ok"], (nama, r))
        self.assertEqual(len(w.catalog), 7)

    def test_t02_pengungkapan_selektif(self):
        """T-02 Verifier hanya menerima atribut yang diminta; data lain tidak bocor"""
        w = mk()
        cid = w.catalog["ijazah_alya"]
        r, pres = w.check(w.employer, w.alya, cid, IJAZAH_PUBLIK)
        self.assertTrue(r["ok"])
        self.assertEqual(sorted(r["revealed"]), sorted(IJAZAH_PUBLIK))
        teks = json.dumps(pres)
        for rahasia in ("DUMMY-0001", "IJZ-DUMMY-0001", "Alya Contoh", "2026-08-20"):
            self.assertNotIn(rahasia, teks)
        # transkrip: kampus tujuan hanya melihat IPK dan SKS, bukan daftar nilai
        r2, pres2 = w.check(w.campus, w.alya, w.catalog["transkrip_alya"], ["ipk", "total_sks"])
        self.assertTrue(r2["ok"])
        self.assertNotIn("Blockchain", json.dumps(pres2))

    def test_t03_pencabutan_dan_penangguhan(self):
        """T-03 Penangguhan, pengaktifan kembali, dan pencabutan permanen"""
        w = mk()
        cid = w.catalog["ijazah_bagas"]
        self.assertTrue(w.check(w.employer, w.bagas, cid, IJAZAH_PUBLIK[:1])[0]["ok"])
        self.assertTrue(w.set_status(w.ict, cid, "SUSPENDED")[0])
        self.assertEqual(w.check(w.employer, w.bagas, cid, [])[0]["code"], "DITANGGUHKAN")
        self.assertTrue(w.set_status(w.ict, cid, "ACTIVE")[0])
        self.assertTrue(w.check(w.employer, w.bagas, cid, [])[0]["ok"])
        self.assertTrue(w.set_status(w.ict, cid, "REVOKED")[0])
        self.assertEqual(w.check(w.employer, w.bagas, cid, [])[0]["code"], "DICABUT")
        ok, why = w.set_status(w.ict, cid, "ACTIVE")          # DICABUT bersifat final
        self.assertFalse(ok)
        self.assertEqual(why, "TRANSISI_STATUS_DITOLAK")

    def test_t04_kedaluwarsa(self):
        """T-04 Sertifikat kompetensi kedaluwarsa setelah masa berlaku"""
        w = mk()
        cid = w.catalog["sertifikat_alya"]
        self.assertTrue(w.check(w.employer, w.alya, cid, [])[0]["ok"])
        w.clock.advance(days=366)
        self.assertEqual(w.check(w.employer, w.alya, cid, [])[0]["code"], "KEDALUWARSA")
        # ijazah tanpa masa berlaku tetap valid
        self.assertTrue(w.check(w.employer, w.alya, w.catalog["ijazah_alya"], [])[0]["ok"])

    def test_t05_pemulihan_kunci_lulusan(self):
        """T-05 Lulusan kehilangan kunci: kredensial lama dicabut, diterbitkan ulang ke kunci baru"""
        w = mk()
        lama = w.catalog["ijazah_alya"]
        kunci_lama = w.alya.key
        claims = dict(w.alya.items[lama]["claims"])
        w.alya.new_key("holder:Alya Contoh#pemulihan")           # kunci baru (setelah verifikasi identitas)
        self.assertTrue(w.set_status(w.ucn, lama, "REVOKED")[0])
        baru = w.issue(w.ucn, w.alya, "Ijazah", claims, name="ijazah_alya_baru")
        self.assertTrue(w.check(w.employer, w.alya, baru, ["gelar"])[0]["ok"])
        # kredensial lama tidak bisa dipakai lagi
        pres = w.alya.present(lama, ["gelar"], w.employer.challenge())
        self.assertEqual(w.employer.verify(pres)["code"], "DICABUT")
        # pemegang kunci lama tidak bisa memakai kredensial baru
        pencuri = Wallet("Alya Contoh", "DUMMY-0001")
        pencuri.key = kunci_lama
        pencuri.items[baru] = w.alya.items[baru]
        r = w.employer.verify(pencuri.present(baru, ["gelar"], w.employer.challenge()))
        self.assertEqual(r["code"], "BUKTI_PEMEGANG_TIDAK_VALID")

    def test_t06_rotasi_kunci_penerbit(self):
        """T-06 Rotasi kunci penerbit terencana: kredensial lama tetap valid, penerbitan baru memakai kunci baru"""
        w = mk()
        lama = w.catalog["ijazah_alya"]
        kunci_baru = Key("Universitas Contoh Nusantara#2")
        ok, _ = w.net.submit(w.ucn.tx("ROTATE_KEY", {"new_pub": kunci_baru.pub}, w.clock))
        self.assertTrue(ok)
        w.ucn.key = kunci_baru
        self.assertTrue(w.check(w.employer, w.alya, lama, [])[0]["ok"])
        baru = w.issue(w.ucn, w.alya, "Ijazah", {"nama": "Alya Contoh", "gelar": "S.Kom."})
        self.assertTrue(w.check(w.employer, w.alya, baru, ["gelar"])[0]["ok"])
        anchor = w.net.query_anchor(baru)
        self.assertEqual(anchor["anchor_key"], kunci_baru.pub)

    def test_t07_interoperabilitas_json(self):
        """T-07 Kredensial diekspor ke JSON dan diverifikasi ulang tanpa objek internal"""
        w = mk()
        cid = w.catalog["ijazah_citra"]
        pres = w.citra.present(cid, ["gelar"], w.campus.challenge())
        dari_json = json.loads(json.dumps(pres))                 # lintas sistem: hanya JSON
        for kunci in ("id", "type", "issuer", "credentialSubject", "proof"):
            self.assertIn(kunci, dari_json["credential"])
        self.assertTrue(w.campus.verify(dari_json)["ok"])

class Keamanan(unittest.TestCase):
    def test_t08_pemalsuan_penerbit(self):
        """T-08 Penerbit tak terdaftar tidak dapat menjangkarkan atau lolos verifikasi"""
        w = mk()
        palsu = Actor("Kampus Palsu Contoh", ["ISSUER"])
        wal = Wallet("Dodi Contoh", "DUMMY-0009")
        cred, salts = build_credential(palsu, wal.did, wal.key.pub, "Ijazah",
                                       {"gelar": "S.Kom."}, w.clock.now(), None, "urn:cred:palsu:1")
        ok, why = w.net.submit(palsu.tx("ANCHOR_CREDENTIAL", anchor_payload(cred), w.clock))
        self.assertFalse(ok)
        self.assertEqual(why, "PENGIRIM_TIDAK_TERDAFTAR")
        wal.store(cred, {"gelar": "S.Kom."}, salts)
        r = w.employer.verify(wal.present("urn:cred:palsu:1", ["gelar"], w.employer.challenge()))
        self.assertEqual(r["code"], "TIDAK_ADA_DI_LEDGER")

    def test_t09_manipulasi_data(self):
        """T-09 Perubahan atribut atau isi kredensial terdeteksi"""
        w = mk()
        cid = w.catalog["transkrip_bagas"]
        pres = w.bagas.present(cid, ["ipk"], w.employer.challenge())
        pres["disclosed"]["ipk"]["value"] = 4.00                  # menaikkan IPK
        self.assertEqual(w.employer.verify(pres)["code"], "ATRIBUT_TIDAK_COCOK_DENGAN_KOMITMEN")
        pres2 = w.bagas.present(cid, ["ipk"], w.employer.challenge())
        pres2["credential"]["credentialSubject"]["commitments"]["ipk"] = "0" * 64
        self.assertEqual(w.employer.verify(pres2)["code"], "HASH_TIDAK_COCOK")

    def test_t10_replay_dan_pencurian_presentasi(self):
        """T-10 Presentasi tidak dapat diulang, dialihkan ke verifier lain, atau dipakai tanpa kunci pemegang"""
        w = mk()
        cid = w.catalog["ijazah_alya"]
        ch = w.employer.challenge()
        pres = w.alya.present(cid, ["gelar"], ch)
        self.assertTrue(w.employer.verify(pres)["ok"])
        self.assertEqual(w.employer.verify(pres)["code"], "REPLAY_ATAU_NONCE_TIDAK_DIKENAL")
        # dialihkan ke verifier lain
        pres2 = w.alya.present(cid, ["gelar"], w.employer.challenge())
        self.assertEqual(w.campus.verify(pres2)["code"], "REPLAY_ATAU_NONCE_TIDAK_DIKENAL")
        # penyadap memakai ulang atribut yang tersadap tetapi tidak punya kunci pemegang
        tercuri = w.alya.present(cid, ["gelar"], w.employer.challenge())
        pencuri = Wallet("Penyadap Contoh", "X")
        ch2 = w.employer.challenge()
        body = {"cred_id": cid, "nonce": ch2["nonce"], "verifier": ch2["verifier"],
                "reveal": ["gelar"]}
        palsu = {"credential": tercuri["credential"], "disclosed": tercuri["disclosed"],
                 "holder_proof": {"body": body, "signature": pencuri.key.sign(canon(body))}}
        self.assertEqual(w.employer.verify(palsu)["code"], "BUKTI_PEMEGANG_TIDAK_VALID")

    def test_t11_otorisasi_lintas_penerbit(self):
        """T-11 Penerbit lain, pengamat, dan non-validator ditolak melakukan aksi di luar wewenang"""
        w = mk()
        cid = w.catalog["ijazah_alya"]                           # milik UCN
        self.assertEqual(w.set_status(w.ict, cid, "REVOKED")[1], "BUKAN_PENERBIT_KREDENSIAL")
        pl = {"cred_id": "urn:cred:x", "type": "Ijazah", "cred_hash": "0" * 64,
              "root": "0" * 64, "expires_at": None, "issuer": w.ucn.did}
        ok, why = w.net.submit(w.lspc.tx("ANCHOR_CREDENTIAL", pl, w.clock))
        self.assertEqual(why, "PENERBIT_TIDAK_SESUAI")
        ok, why = w.net.submit(w.opc.tx("SET_STATUS", {"cred_id": cid, "status": "REVOKED"}, w.clock))
        self.assertEqual(why, "HANYA_BACA")
        self.assertEqual(w.net.query_anchor(cid)["status"], "ACTIVE")

    def test_t12_kompromi_kunci_penerbit(self):
        """T-12 Kunci penerbit dikompromikan: penerbitan sejak waktu kompromi tidak sah, sebelumnya tetap sah"""
        w = mk()
        sebelum = w.catalog["ijazah_alya"]
        # penyerang memakai kunci curian menerbitkan kredensial sebelum tata kelola bertindak
        korban = Wallet("Korban Contoh", "DUMMY-0100")
        palsu = w.issue(w.ucn, korban, "Ijazah", {"gelar": "S.Kom. (palsu)"}, name="palsu")
        tinggi_palsu = w.net.query_anchor(palsu)["anchored_height"]
        ok, why = w.gov(w.ict, "FLAG_KEY_COMPROMISED",
                        {"target": w.ucn.did, "from_height": tinggi_palsu}, [w.ict, w.pcm, w.lspc])
        self.assertTrue(ok, why)
        self.assertEqual(w.check(w.employer, korban, palsu, [])[0]["code"],
                         "KUNCI_PENERBIT_DIKOMPROMIKAN")
        self.assertTrue(w.check(w.employer, w.alya, sebelum, [])[0]["ok"])
        # kunci curian tidak dapat lagi mengirim transaksi
        ok, why = w.net.submit(w.ucn.tx("SET_STATUS", {"cred_id": sebelum, "status": "REVOKED"}, w.clock))
        self.assertEqual(why, "KUNCI_DIKOMPROMIKAN")
        # pemulihan: kunci pengganti disetujui kuorum validator
        baru = Key("Universitas Contoh Nusantara#pengganti")
        ok, why = w.gov(w.ict, "REPLACE_KEY", {"target": w.ucn.did, "new_pub": baru.pub},
                        [w.ict, w.pcm, w.lspc])
        self.assertTrue(ok, why)
        w.ucn.key = baru
        pulih = w.issue(w.ucn, w.alya, "Ijazah", {"gelar": "S.Kom."})
        self.assertTrue(w.check(w.employer, w.alya, pulih, ["gelar"])[0]["ok"])

    def test_t13_pemalsuan_riwayat_ledger(self):
        """T-13 Perubahan riwayat blok pada satu node terdeteksi"""
        w = mk()
        rep, ok = w.net.consistency_report()
        self.assertTrue(ok)
        node = w.net.nodes[w.pcm.did]
        node.chain[3]["txs"][0]["payload"]["type"] = "IjazahPalsu"
        valid, pesan = node.verify_chain()
        self.assertFalse(valid)
        rep, ok = w.net.consistency_report()
        self.assertFalse(ok)
        self.assertFalse(rep[node.name]["rantai_valid"])

    def test_t14_pemalsuan_log_audit(self):
        """T-14 Log audit berantai-hash; perubahan entri terdeteksi dan log tidak memuat nilai atribut"""
        w = mk()
        w.check(w.employer, w.alya, w.catalog["ijazah_alya"], IJAZAH_PUBLIK)
        w.check(w.campus, w.alya, w.catalog["transkrip_alya"], ["ipk"])
        self.assertTrue(w.audit.verify())
        teks = json.dumps(w.audit.entries)
        for rahasia in ("S1 Informatika", "3.72", "DUMMY-0001"):
            self.assertNotIn(rahasia, teks)
        w.audit.entries[0]["event"]["hasil"] = "OK-PALSU"
        self.assertFalse(w.audit.verify())

    def test_t15_privasi_on_chain(self):
        """T-15 Seluruh ledger tidak memuat data pribadi lulusan maupun identitas pemegang"""
        w = mk()
        for node in w.net.nodes.values():
            teks = json.dumps(node.chain, ensure_ascii=False)
            for rahasia in ("Alya Contoh", "Bagas Contoh", "Citra Contoh", "DUMMY-000",
                            "IJZ-DUMMY", "3.72", "holder", "S1 Informatika"):
                self.assertNotIn(rahasia, teks, (node.name, rahasia))

class JaringanDanTataKelola(unittest.TestCase):
    def test_t16_onboarding_dengan_kuorum(self):
        """T-16 Anggota baru hanya masuk bila disetujui kuorum validator (3 dari 4)"""
        w = mk()
        anggota = {"did": w.ucb.did, "name": w.ucb.name, "roles": w.ucb.roles, "pub": w.ucb.key.pub}
        ok, why = w.gov(w.ucn, "ADD_MEMBER", {"member": anggota}, [w.ucn])
        self.assertEqual(why, "KUORUM_TIDAK_TERPENUHI")
        ok, why = w.net.submit(w.ucb.tx("ADD_MEMBER", {"proposal": {}, "votes": {}}, w.clock))
        self.assertEqual(why, "PENGIRIM_TIDAK_TERDAFTAR")
        ok, why = w.gov(w.ucn, "ADD_MEMBER", {"member": anggota}, [w.ucn, w.ict, w.pcm])
        self.assertTrue(ok, why)
        self.assertTrue(w.issue(w.ucb, w.citra, "Ijazah", {"gelar": "S.Pd."}) is not None)
        ok, why = w.gov(w.ucn, "DEACTIVATE_MEMBER", {"target": w.ucb.did}, [w.ucn, w.ict, w.pcm])
        self.assertTrue(ok, why)
        with self.assertRaises(RuntimeError):                    # nonaktif tidak boleh menerbitkan
            w.issue(w.ucb, w.citra, "Ijazah", {"gelar": "S.Pd."})

    def test_t17_toleransi_kegagalan_node(self):
        """T-17 Konsensus mayoritas: 1 node mati tetap commit; 2 node mati menolak commit; node pulih menyusul"""
        w = mk()
        h0 = w.net.height()
        w.net.nodes[w.pcm.did].online = False
        cid = w.issue(w.ucn, w.alya, "Ijazah", {"gelar": "S.Kom."})
        self.assertEqual(w.net.height(), h0 + 1)
        w.net.nodes[w.lspc.did].online = False
        with self.assertRaises(RuntimeError):
            w.issue(w.ucn, w.alya, "Ijazah", {"gelar": "S.Kom."})
        self.assertEqual(w.net.height(), h0 + 1)                 # tidak ada blok baru
        w.net.recover(w.pcm.did)
        w.net.recover(w.lspc.did)
        rep, ok = w.net.consistency_report()
        self.assertTrue(ok, rep)
        self.assertIsNotNone(w.net.nodes[w.pcm.did].state.creds.get(cid))

class Performa(unittest.TestCase):
    def test_t18_throughput_dan_latensi_simulasi(self):
        """T-18 Throughput terbit dan latensi verifikasi pada simulasi dummy (satu proses)"""
        r = benchmark(n=300, batch=50)
        print("\n    [T-18] hasil: n=%(n)d, blok=%(blok)d, node=%(node)d, terbit=%(issue_tps).0f tx/dtk, "
              "verifikasi rerata=%(verify_mean_ms).2f ms, p95=%(verify_p95_ms).2f ms, "
              "maks=%(verify_max_ms).2f ms" % r)
        self.assertGreaterEqual(r["issue_tps"], 50)              # kriteria: >= 50 tx/dtk
        self.assertLess(r["verify_p95_ms"], 50)                  # kriteria: p95 < 50 ms

if __name__ == "__main__":
    unittest.main(verbosity=2)
