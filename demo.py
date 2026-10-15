"""
demo.py - Skenario ujung ke ujung dengan data DUMMY. Jalankan: python demo.py
"""
import json
from kredensial_sim import Key
from data_dummy import World, benchmark

def judul(t):
    print("\n=== %s ===" % t)

def ringkas(r):
    return "%s%s" % (r["code"], (" | terungkap: " + json.dumps(r["revealed"], ensure_ascii=False)) if r["revealed"] else "")

w = World()
judul("1. Jaringan konsorsium (simulasi, dummy)")
for n in w.net.nodes.values():
    print("  node %-38s peran=%-22s tinggi=%d" % (n.name, "+".join(n.actor.roles), n.height()))
print("  validator=%d, kuorum konsensus=%d (mayoritas), kuorum tata kelola=%d (2/3)" % (
    w.net.total_validators, w.net.quorum(), w.net.read_node().state.quorum_gov()))

judul("2. Penerbitan 7 kredensial dummy (ijazah, transkrip, sertifikat)")
w.populate()
for nama, cid in w.catalog.items():
    a = w.net.query_anchor(cid)
    print("  %-18s %-22s penerbit=%-36s blok=%d" % (nama, a["type"], w.net.query_member(a["issuer"])["name"], a["anchored_height"]))
contoh = w.net.query_anchor(w.catalog["ijazah_alya"])
print("\n  Isi catatan on-chain untuk satu ijazah (hanya hash dan metadata, tanpa data pribadi):")
print("  " + json.dumps({k: (v[:16] + "...") if isinstance(v, str) and len(v) > 40 else v for k, v in contoh.items()}, ensure_ascii=False))

judul("3. Pengungkapan selektif")
r, p = w.check(w.employer, w.alya, w.catalog["ijazah_alya"], ["program_studi", "gelar", "status_kelulusan"])
print("  Pemberi kerja (ijazah)  :", ringkas(r))
r, p = w.check(w.campus, w.alya, w.catalog["transkrip_alya"], ["ipk", "total_sks"])
print("  Kampus tujuan (transkrip):", ringkas(r))
r, p = w.check(w.employer, w.alya, w.catalog["sertifikat_alya"], ["skema", "hasil"])
print("  Pemberi kerja (sertifikat):", ringkas(r))

judul("4. Penangguhan dan pencabutan")
cid = w.catalog["ijazah_bagas"]
w.set_status(w.ict, cid, "SUSPENDED"); print("  setelah ditangguhkan :", w.check(w.employer, w.bagas, cid, [])[0]["code"])
w.set_status(w.ict, cid, "ACTIVE");    print("  setelah diaktifkan   :", w.check(w.employer, w.bagas, cid, [])[0]["code"])
w.set_status(w.ict, cid, "REVOKED");   print("  setelah dicabut      :", w.check(w.employer, w.bagas, cid, [])[0]["code"])

judul("5. Kedaluwarsa (jam simulasi maju 366 hari)")
w.clock.advance(days=366)
print("  sertifikat Alya:", w.check(w.employer, w.alya, w.catalog["sertifikat_alya"], [])[0]["code"])
print("  ijazah Alya     :", w.check(w.employer, w.alya, w.catalog["ijazah_alya"], [])[0]["code"])

judul("6. Pemulihan kunci lulusan (Citra kehilangan kunci)")
lama = w.catalog["ijazah_citra"]
claims = dict(w.citra.items[lama]["claims"])
w.citra.new_key("holder:Citra Contoh#pemulihan")
w.set_status(w.pcm, lama, "REVOKED")
baru = w.issue(w.pcm, w.citra, "Ijazah", claims)
print("  kredensial lama :", w.employer.verify(w.citra.present(lama, [], w.employer.challenge()))["code"])
print("  kredensial baru :", w.check(w.employer, w.citra, baru, ["gelar"])[0]["code"])

judul("7. Kompromi kunci penerbit dan pemulihannya")
korban = w.alya
palsu = w.issue(w.ucn, korban, "Ijazah", {"gelar": "S.Kom. (diterbitkan dengan kunci curian)"})
tinggi = w.net.query_anchor(palsu)["anchored_height"]
ok, _ = w.gov(w.ict, "FLAG_KEY_COMPROMISED", {"target": w.ucn.did, "from_height": tinggi}, [w.ict, w.pcm, w.lspc])
print("  tata kelola menandai kunci UCN dikompromikan sejak blok %d: %s" % (tinggi, "disetujui" if ok else "ditolak"))
print("  kredensial sebelum kompromi :", w.check(w.employer, w.alya, w.catalog["transkrip_alya"], [])[0]["code"])
print("  kredensial sejak kompromi   :", w.check(w.employer, korban, palsu, [])[0]["code"])
print("  transaksi dengan kunci curian:", w.net.submit(w.ucn.tx("SET_STATUS", {"cred_id": palsu, "status": "REVOKED"}, w.clock))[1])
baru_kunci = Key("Universitas Contoh Nusantara#pengganti")
ok, _ = w.gov(w.ict, "REPLACE_KEY", {"target": w.ucn.did, "new_pub": baru_kunci.pub}, [w.ict, w.pcm, w.lspc])
w.ucn.key = baru_kunci
print("  kunci pengganti disetujui kuorum:", ok)

judul("8. Kegagalan node (konsensus mayoritas)")
tinggi0 = w.net.height()
w.net.nodes[w.pcm.did].online = False
w.issue(w.ucn, w.alya, "Ijazah", {"gelar": "S.Kom."}); print("  1 node mati  : commit berhasil, tinggi %d -> %d" % (tinggi0, w.net.height()))
w.net.nodes[w.lspc.did].online = False
try:
    w.issue(w.ucn, w.alya, "Ijazah", {"gelar": "S.Kom."})
except RuntimeError as e:
    print("  2 node mati  : %s (tinggi tetap %d)" % (e, w.net.height()))
w.net.recover(w.pcm.did); w.net.recover(w.lspc.did)
rep, ok = w.net.consistency_report()
print("  setelah pulih : konsisten=%s" % ok)
for nama, v in rep.items():
    print("    %-38s tinggi=%d head=%s rantai_valid=%s" % (nama, v["tinggi"], v["head"], v["rantai_valid"]))

judul("9. Log audit verifier (berantai-hash, tanpa nilai atribut)")
print("  jumlah entri=%d, utuh=%s" % (len(w.audit.entries), w.audit.verify()))
print("  contoh entri:", json.dumps(w.audit.entries[0]["event"], ensure_ascii=False))

judul("10. Kecepatan simulasi (satu proses, di memori; bukan tolok ukur jaringan nyata)")
b = benchmark(300, 50)
print("  n=%(n)d, blok=%(blok)d, node=%(node)d" % b)
print("  throughput terbit  : %.0f tx/dtk" % b["issue_tps"])
print("  latensi verifikasi : rerata %.2f ms, p95 %.2f ms, maks %.2f ms" % (b["verify_mean_ms"], b["verify_p95_ms"], b["verify_max_ms"]))
