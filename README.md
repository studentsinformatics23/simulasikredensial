# Simulasi Dummy Sistem Verifikasi Kredensial Akademik

Proyek ini adalah **simulasi** untuk UTS Blockchain (Bagian B). Seluruh nama, nomor, dan kunci
bersifat **fiktif**. Tidak ada koneksi ke jaringan blockchain, layanan, atau lembaga yang nyata.
Semuanya berjalan di memori dan tidak menyimpan apa pun ke disk.

## Batas simulasi (baca dulu)
- Konsensus disederhanakan: pemimpin bergilir dan persetujuan mayoritas validator. Ini **bukan**
  implementasi Raft atau BFT yang sebenarnya.
- Kunci Ed25519 dibuat deterministik dari nama agar hasil dapat diulang. Jangan dipakai di tempat lain.
- Angka kecepatan berasal dari satu proses di memori tanpa jaringan, sehingga **tidak mewakili**
  kinerja jaringan nyata.
- Tidak ada penyimpanan kunci aman (HSM), tidak ada kanal jaringan, dan tidak ada verifikasi formal.

## Menjalankan
```
pip install cryptography        # diuji dengan cryptography 46.0.6, Python 3.12
python -m unittest -v           # 18 uji (T-01 sampai T-18)
python demo.py                  # skenario ujung ke ujung
python uji_mutasi.py            # 10 mutan, memeriksa apakah uji menangkap kesalahan
```

## Isi
| Berkas | Fungsi |
|---|---|
| `kredensial_sim.py` | Inti: kunci, transaksi, state ledger, blok, node, jaringan, kredensial, dompet, verifier, log audit |
| `data_dummy.py` | Dunia dummy: 4 penerbit-validator, 1 pengamat, 3 lulusan, 2 verifier, 7 kredensial, benchmark |
| `test_kredensial_sim.py` | 18 uji (fungsional, keamanan, jaringan dan tata kelola, performa) |
| `uji_mutasi.py` | Uji mutasi manual |
| `demo.py` | Skenario demonstrasi |
| `hasil_uji.txt`, `hasil_mutasi.txt`, `hasil_demo.txt` | Keluaran yang dijalankan saat laporan disusun |

## Peta uji ke ancaman (lihat matriks ancaman di laporan)
| Ancaman | Uji |
|---|---|
| TM-01 Pemalsuan kredensial atau penerbit palsu | T-08, T-09 |
| TM-02 Kunci penerbit dikompromikan | T-06, T-12 |
| TM-03 Presentasi dicuri atau diulang, kunci lulusan hilang | T-05, T-10 |
| TM-04 Kebocoran data pribadi dan korelasi | T-02, T-15 |
| TM-05 Penyalahgunaan wewenang antar anggota | T-11, T-16 |
| TM-06 Perubahan riwayat ledger atau log audit | T-13, T-14 |
| TM-07 Gangguan ketersediaan node | T-17 |
