import streamlit as st
import os
from encoder import encoder
from decoder import decoder

# --- Konfigurasi Halaman ---
st.set_page_config(
    page_title="Steganography App",
    page_icon="🔒",
    layout="wide"
)

st.title("Aplikasi Steganografi F5 & optimDMCSS")
st.caption("Dibuat oleh AI untuk Muhammad Rizki Al-Fathir")


# --- Inisialisasi Session State ---
# Ini untuk menyimpan hasil agar tidak hilang saat script rerun
if 'stego_image_bytes' not in st.session_state:
    st.session_state.stego_image_bytes = None
if 'path_key_bytes' not in st.session_state:
    st.session_state.path_key_bytes = None


# --- Pilihan Mode di Sidebar ---
mode = st.sidebar.radio("Pilih Mode:", ("Embed (Sembunyikan Pesan)", "Extract (Ekstrak Pesan)"))

# --- Direktori Temporary untuk Menyimpan File ---
TEMP_DIR = "temp_files"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# --- Opsi Algoritma ---
ALGO_OPTIONS = {
    "F5": 0,
    "optimDMCSS": 2
}

def clear_embed_results():
    """
    Mengatur ulang session state DAN menghapus file fisik yang tersisa
    dari proses embed sebelumnya.
    """
    # --- Langkah 1: Hapus file fisik dari direktori ---
    stego_image_path = os.path.join(TEMP_DIR, "output_stego.jpg")
    path_key_path = "path_key.bin"  # File ini ada di direktori utama

    # Hapus gambar stego jika ada
    try:
        if os.path.exists(stego_image_path):
            os.remove(stego_image_path)
    except Exception as e:
        st.warning(f"Gagal menghapus file gambar stego: {e}")

    # Hapus file path_key.bin jika ada
    try:
        if os.path.exists(path_key_path):
            os.remove(path_key_path)
    except Exception as e:
        st.warning(f"Gagal menghapus file kunci path: {e}")

    # --- Langkah 2: Atur ulang session state seperti sebelumnya ---
    st.session_state.stego_image_bytes = None
    st.session_state.path_key_bytes = None
    
    # Beri notifikasi bahwa pembersihan berhasil
    st.toast("Hasil dan file sementara telah dibersihkan.")

if mode == "Embed (Sembunyikan Pesan)":
    st.header("🖼️ Mode Embed: Sembunyikan Pesan ke dalam Gambar")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Upload Gambar Asli (Cover)")
        uploaded_cover_image = st.file_uploader("Pilih file gambar...", type=["jpg", "jpeg", "png"])

        st.subheader("Pilih Opsi")
        selected_algo_name = st.selectbox("Pilih Algoritma Steganografi:", ALGO_OPTIONS.keys())
        use_rs = st.checkbox("Gunakan Reed-Solomon untuk koreksi kesalahan?", value=True)

    with col2:
        st.subheader("Masukkan Pesan & Kunci")
        message = st.text_area("Pesan Rahasia:")
        key = st.text_input("Kunci Rahasia (16, 24, atau 32 karakter)", type="password")

    if st.button("Sembunyikan Pesan", type="primary"):
        # Reset state sebelumnya saat tombol ditekan lagi
        st.session_state.stego_image_bytes = None
        st.session_state.path_key_bytes = None

        if uploaded_cover_image and message and key:
            if len(key) not in [16, 24, 32]:
                st.error("Error: Panjang kunci harus 16, 24, atau 32 karakter.")
            else:
                with st.spinner("Memproses gambar dan menyembunyikan pesan... Ini mungkin memakan waktu beberapa saat."):
                    try:
                        cover_image_path = os.path.join(TEMP_DIR, uploaded_cover_image.name)
                        with open(cover_image_path, "wb") as f:
                            f.write(uploaded_cover_image.getbuffer())

                        enc = encoder(block_size=8, rs_param=256)
                        enc.encode(
                            img_name=cover_image_path,
                            message_string=message,
                            key=key.encode('utf-8'),
                            func=ALGO_OPTIONS[selected_algo_name],
                            verbose=False,
                            use_rs=use_rs,
                            output_name=os.path.join(TEMP_DIR, "output_stego")
                        )

                        # --- SIMPAN HASIL KE SESSION STATE ---
                        stego_image_path = os.path.join(TEMP_DIR, "output_stego.jpg")
                        path_key_path = "path_key.bin"

                        with open(stego_image_path, "rb") as f_img:
                            st.session_state.stego_image_bytes = f_img.read()
                        with open(path_key_path, "rb") as f_key:
                            st.session_state.path_key_bytes = f_key.read()

                    except Exception as e:
                        st.error(f"Terjadi kesalahan saat embedding: {e}")
        else:
            st.warning("Harap lengkapi semua input: upload gambar, isi pesan, dan masukkan kunci.")

    # --- Tampilkan hasil JIKA ada di session_state ---
    # Blok ini sekarang ada di luar 'if st.button'
    if st.session_state.stego_image_bytes and st.session_state.path_key_bytes:
        st.success("Pesan berhasil disembunyikan! Unduh file di bawah ini.")

        # Gunakan kolom untuk menata hasil
        res_col1, res_col2 = st.columns([1, 2])

        with res_col1:
            st.subheader("Hasil:")
            st.image(st.session_state.stego_image_bytes, caption="Gambar Stego")

        with res_col2:
            st.subheader("Download Files:")
            st.info("PENTING: Anda memerlukan **kedua file** di bawah ini untuk mengekstrak pesan kembali.")

            # Tombol download sekarang menggunakan data dari session state
            st.download_button(
                label="⬇️ Download Gambar Stego (.jpg)",
                data=st.session_state.stego_image_bytes,
                file_name="stego_image.jpg",
                mime="image/jpeg",
                key="download_stego_img" # Tambahkan key unik
            )
            st.download_button(
                label="🔑 Download Kunci Path (.bin)",
                data=st.session_state.path_key_bytes,
                file_name="path_key.bin",
                mime="application/octet-stream",
                key="download_path_key" # Tambahkan key unik
            )

            st.divider()

            # Tombol untuk menghapus hasil secara manual
            st.button("Hapus Hasil & Mulai Lagi", on_click=clear_embed_results, type="secondary")


        
        st.info("PENTING: Anda memerlukan **kedua file** di atas untuk mengekstrak pesan kembali.")


# Kode untuk mode 'Extract' tidak perlu diubah, jadi saya akan memotongnya agar ringkas.
# Pastikan Anda menyalin seluruh kode yang sudah Anda miliki untuk bagian ini.
elif mode == "Extract (Ekstrak Pesan)":
    st.header("🔍 Mode Extract: Ekstrak Pesan dari Gambar")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Upload File")
        uploaded_stego_image = st.file_uploader("Upload Gambar Stego (.jpg)", type=["jpg", "jpeg"])
        uploaded_path_key = st.file_uploader("Upload File Kunci Path (.bin)", type=["bin"])

    with col2:
        st.subheader("Masukkan Kunci & Opsi")
        key_extract = st.text_input("Kunci Rahasia:", type="password")
        selected_algo_name_extract = st.selectbox("Algoritma yang digunakan saat embed:", ALGO_OPTIONS.keys())
        use_rs_extract = st.checkbox("Apakah Reed-Solomon digunakan saat embed?", value=True)
    
    st.info("Pastikan Kunci, Algoritma, dan opsi Reed-Solomon sama persis seperti saat proses embed.")

    if st.button("Ekstrak Pesan", type="primary"):
        if uploaded_stego_image and uploaded_path_key and key_extract:
            with st.spinner("Membaca gambar dan mengekstrak pesan..."):
                try:
                    stego_image_path = os.path.join(TEMP_DIR, "uploaded_stego.jpg")
                    path_key_path = "path_key.bin"

                    with open(stego_image_path, "wb") as f:
                        f.write(uploaded_stego_image.getbuffer())
                    with open(path_key_path, "wb") as f:
                        f.write(uploaded_path_key.getbuffer())

                    dec = decoder(block_size=8, rs_param=256)
                    message_out = dec.decode(
                        img=stego_image_path,
                        path_key_bin=path_key_path,
                        key=key_extract.encode('utf-8'),
                        func=ALGO_OPTIONS[selected_algo_name_extract],
                        use_rs=use_rs_extract,
                        greyscale=False
                    )

                    st.success("Pesan berhasil diekstrak!")
                    st.subheader("Pesan yang Ditemukan:")
                    st.text_area("", value=message_out, height=200, disabled=True)

                except Exception as e:
                    st.error(f"Gagal mengekstrak pesan. Error: {e}")
                    st.warning("Pastikan kunci, algoritma, dan file yang diupload sudah benar.")
        else:
            st.warning("Harap lengkapi semua input: upload gambar stego, file kunci, dan masukkan kunci.")