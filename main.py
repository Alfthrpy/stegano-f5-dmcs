import streamlit as st
import os
import tempfile
from PIL import Image
import io
import traceback  # Tambahkan di bagian atas file

# Pastikan Anda sudah membuat direktori stegano_core
# dan menempatkan semua file .py dari repo di sana.
from bulbul.encoder import encoder as encoder_class
from bulbul.decoder import decoder as decoder_class


# Inisialisasi objek encoder dan decoder
# BLOCK_SIZE dan RS_PARAM bisa disesuaikan jika perlu
# Nilai default dari repo adalah (8, 256)
encoder_obj = encoder_class(8, 256)
decoder_obj = decoder_class(8, 256)

def embed_message_in_image(cover_image_bytes, message_string):
    """
    Fungsi pembungkus untuk menyematkan pesan ke dalam gambar.
    Bekerja dengan data bytes di memori.
    """
    try:
        # Buat file temporer untuk gambar sampul dan pesan
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as temp_cover_file:
            temp_cover_file.write(cover_image_bytes)
            temp_cover_path = temp_cover_file.name

        with tempfile.NamedTemporaryFile(delete=False, mode="w+", suffix=".txt") as temp_msg_file:
            temp_msg_file.write(message_string)
            temp_msg_path = temp_msg_file.name
        
        # Tentukan path output temporer
        output_dir = tempfile.gettempdir()
        output_stego_path = os.path.join(output_dir, "stego_image.jpg")
        
        # Panggil metode encode dari library
        # func=0 adalah untuk algoritma F5 standar
        # verbose=False agar outputnya adalah file gambar, bukan .txt
        # use_rs=False agar tidak menggunakan Reed-Solomon (sesuai permintaan F5 standar)
        encoder_obj.encode(
            img_name=temp_cover_path,
            message_path=temp_msg_path,
            func=0, 
            verbose=False, 
            use_rs=False,
            output_name=os.path.join(output_dir, "stego_image") # nama tanpa ekstensi
        )

        # Metode encode menghasilkan 'path_key.bin' di direktori kerja.
        # Kita perlu memindahkannya atau membacanya.
        key_path_original = "path_key.bin"
        
        # Baca gambar stego dan kunci yang dihasilkan ke dalam memori
        with open(output_stego_path, "rb") as f:
            stego_image_bytes = f.read()

        with open(key_path_original, "rb") as f:
            key_bytes = f.read()

        # Hapus file temporer
        os.remove(temp_cover_path)
        os.remove(temp_msg_path)
        os.remove(output_stego_path)
        os.remove(key_path_original)
        
        return stego_image_bytes, key_bytes

    except Exception as e:
        # Bersihkan file temporer jika terjadi error
        if 'temp_cover_path' in locals() and os.path.exists(temp_cover_path):
            os.remove(temp_cover_path)
        if 'temp_msg_path' in locals() and os.path.exists(temp_msg_path):
            os.remove(temp_msg_path)
        st.error(f"Terjadi kesalahan saat embedding: {e}")
        st.text(traceback.format_exc())
        print
        st.info("Pastikan pesan tidak terlalu panjang untuk ukuran gambar yang diberikan.")
        return None, None


def extract_message_from_image(stego_image_bytes, key_bytes):
    """
    Fungsi pembungkus untuk mengekstrak pesan dari gambar.
    """
    try:
        # Buat file temporer untuk gambar stego dan kuncinya
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_stego_file:
            temp_stego_file.write(stego_image_bytes)
            temp_stego_path = temp_stego_file.name

        # Nama file kunci harus 'path_key.bin' karena di-hardcode di decoder
        with open("path_key.bin", "wb") as temp_key_file:
            temp_key_file.write(key_bytes)
            
        # Panggil metode decode dari library
        # output_file adalah nama untuk file teks hasil ekstraksi
        extracted_message = decoder_obj.decode(
            img=os.path.splitext(temp_stego_path)[0], # nama tanpa ekstensi
            key=b'kunci-rahasia-tidak-digunakan-di-sini-tapi-wajib-ada', # placeholder, karena path dienkripsi
            func=0,
            verbose=False,
            use_rs=False,
            output_file="extracted_message"
        )

        # Hapus file temporer
        os.remove(temp_stego_path)
        os.remove("path_key.bin")
        
        return extracted_message

    except FileNotFoundError:
        st.error("Gagal menemukan file 'path_key.bin'. Pastikan file kunci yang benar telah diunggah.")
        # Hapus file sisa jika ada
        if 'temp_stego_path' in locals() and os.path.exists(temp_stego_path):
            os.remove(temp_stego_path)
        if os.path.exists("path_key.bin"):
            os.remove("path_key.bin")
        return None
    except Exception as e:
        st.error(f"Terjadi kesalahan saat ekstraksi: {e}")
        return None


# --- UI STREAMLIT ---
st.set_page_config(layout="wide", page_title="Aplikasi Steganografi F5")

st.title("🖼️ Aplikasi Steganografi F5")
st.write("Aplikasi ini menggunakan algoritma F5 untuk menyembunyikan pesan di dalam gambar JPEG.")
st.write("---")

# Gunakan kolom untuk tata letak yang lebih baik
col1, col2 = st.columns(2)

with col1:
    st.header("1. Sematkan Pesan (Embed)")
    
    cover_image_upload = st.file_uploader("Unggah Gambar Sampul (Cover Image)", type=['png', 'jpg', 'jpeg', 'bmp'])
    message_text = st.text_area("Masukkan Pesan Rahasia Anda di Sini")
    
    embed_button = st.button("Sematkan Pesan!", key="embed")

    if embed_button and cover_image_upload and message_text:
        with st.spinner("Sedang memproses... Ini mungkin memakan waktu beberapa saat."):
            cover_bytes = cover_image_upload.getvalue()
            
            stego_bytes, key_bytes = embed_message_in_image(cover_bytes, message_text)
            
            if stego_bytes and key_bytes:
                st.session_state.stego_image = stego_bytes
                st.session_state.key = key_bytes
                st.success("Pesan berhasil disematkan!")

    if 'stego_image' in st.session_state and 'key' in st.session_state:
        st.subheader("Hasil Embedding")
        st.image(st.session_state.stego_image, caption="Gambar Stego (Sudah berisi pesan)")
        
        # Tombol download untuk gambar stego dan kunci
        st.download_button(
            label="Unduh Gambar Stego (.jpg)",
            data=st.session_state.stego_image,
            file_name="stego_image.jpg",
            mime="image/jpeg"
        )
        st.download_button(
            label="️Unduh File Kunci (.bin)",
            data=st.session_state.key,
            file_name="path_key.bin",
            mime="application/octet-stream"
        )
        st.warning("**PENTING**: Simpan file kunci! Anda membutuhkannya untuk mengekstrak pesan.")


with col2:
    st.header("2. Ekstrak Pesan (Extract)")
    
    stego_image_upload = st.file_uploader("Unggah Gambar Stego", type=['jpg', 'jpeg'])
    key_file_upload = st.file_uploader("Unggah File Kunci (.bin)", type=['bin'])
    
    extract_button = st.button("Ekstrak Pesan!", key="extract")

    if extract_button and stego_image_upload and key_file_upload:
        with st.spinner("Mengekstrak pesan..."):
            stego_bytes = stego_image_upload.getvalue()
            key_bytes = key_file_upload.getvalue()
            
            extracted_msg = extract_message_from_image(stego_bytes, key_bytes)
            
            if extracted_msg:
                st.success("Pesan berhasil diekstrak!")
                st.subheader("Pesan yang Ditemukan:")
                st.code(extracted_msg, language=None) # Tampilkan dalam blok kode agar mudah dibaca
            else:
                st.error("Ekstraksi gagal. Pastikan gambar stego dan file kunci sudah benar.")
