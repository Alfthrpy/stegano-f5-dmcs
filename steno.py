import streamlit as st
import numpy as np
from PIL import Image
import io
import base64
import hashlib
import struct
from scipy.fftpack import dct, idct
import cv2
import bulbul 
from Crypto.Cipher import AES

class F5Steganography:
    def __init__(self, password="default"):
        self.password = password
        self.seed = self._generate_seed(password)
        
    def _generate_seed(self, password):
        """Generate seed dari password untuk PRNG"""
        return int(hashlib.md5(password.encode()).hexdigest()[:8], 16)
    
    def _string_to_bits(self, text):
        """Konversi string ke bit array dengan length header"""
        # Tambahkan length header (32 bit untuk panjang string)
        length = len(text)
        length_bits = []
        for i in range(32):
            length_bits.append((length >> (31-i)) & 1)
        
        # Konversi string ke bits
        text_bits = []
        for char in text:
            byte_val = ord(char)
            for i in range(8):
                text_bits.append((byte_val >> (7-i)) & 1)
        
        return length_bits + text_bits
    
    def _bits_to_string(self, bits):
        """Konversi bit array ke string dengan length header"""
        if len(bits) < 32:
            return ""
        
        # Extract length dari 32 bit pertama
        length = 0
        for i in range(32):
            length = (length << 1) | bits[i]
        
        if length <= 0 or length > 10000:  # Sanity check
            return ""
        
        # Extract string berdasarkan length
        text_bits = bits[32:32 + (length * 8)]
        if len(text_bits) < length * 8:
            return ""
        
        text = ""
        for i in range(0, len(text_bits), 8):
            if i + 8 <= len(text_bits):
                byte_val = 0
                for j in range(8):
                    byte_val = (byte_val << 1) | text_bits[i + j]
                text += chr(byte_val)
        
        return text
    
    def _get_shuffled_indices(self, total_coeffs, seed):
        """Generate shuffled indices untuk permutasi"""
        np.random.seed(seed)
        indices = list(range(1, total_coeffs))  # Skip DC coefficient (index 0)
        np.random.shuffle(indices)
        return indices
    
    def _embed_bit_in_coeff(self, coeff, bit):
        """Embed single bit dalam koefisien DCT menggunakan F5 method"""
        if coeff == 0:
            return coeff
        
        # F5 algorithm: modify coefficient berdasarkan bit yang ingin di-embed
        abs_coeff = abs(coeff)
        sign = 1 if coeff > 0 else -1
        
        # Check if current LSB matches desired bit
        current_lsb = abs_coeff % 2
        
        if current_lsb != bit:
            # Need to modify coefficient
            if abs_coeff == 1:
                # If coefficient is 1 or -1, set to 0 (shrinkage)
                return 0
            else:
                # Decrease absolute value by 1
                new_abs = abs_coeff - 1
                return new_abs * sign
        
        return coeff
    
    def _extract_bit_from_coeff(self, coeff):
        """Extract bit dari koefisien DCT"""
        if coeff == 0:
            return 0
        return abs(int(coeff)) % 2
    
    def embed_message(self, image, message):
        """Embed pesan ke dalam gambar menggunakan F5"""
        if len(message) == 0:
            raise ValueError("Pesan tidak boleh kosong")
        
        # Konversi ke RGB dan pastikan hanya 3 channels
        if image.mode == 'RGBA':
            # Untuk RGBA, convert ke RGB dengan background putih
            background = Image.new('RGB', image.size, (255, 255, 255))
            background.paste(image, mask=image.split()[-1])
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Double check: pastikan gambar benar-benar RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Konversi ke array numpy dan pastikan shape (H, W, 3)
        img_array = np.array(image, dtype=np.float32)
        if len(img_array.shape) != 3 or img_array.shape[2] != 3:
            raise ValueError(f"Error: Gambar harus RGB. Shape saat ini: {img_array.shape}")
        
        # Konversi pesan ke bits dengan length header
        message_bits = self._string_to_bits(message)
        
        # Bekerja dengan channel hijau (indeks 1)
        green_channel = img_array[:, :, 1]
        
        # Bagi gambar menjadi blok 8x8 untuk DCT
        h, w = green_channel.shape
        h_blocks = h // 8
        w_blocks = w // 8
        
        # Collect all DCT coefficients
        all_coeffs = []
        block_positions = []
        
        for i in range(h_blocks):
            for j in range(w_blocks):
                block = green_channel[i*8:(i+1)*8, j*8:(j+1)*8]
                dct_block = dct(dct(block.T, norm='ortho').T, norm='ortho')
                
                # Flatten block dan simpan posisi
                flat_block = dct_block.flatten()
                for k, coeff in enumerate(flat_block):
                    if k != 0 and abs(coeff) > 0.5:  # Skip DC dan koefisien kecil
                        all_coeffs.append([coeff, i, j, k])
        
        if len(all_coeffs) < len(message_bits):
            raise ValueError(f"Gambar terlalu kecil. Butuh {len(message_bits)} koefisien, tersedia {len(all_coeffs)}")
        
        # Shuffle coefficients berdasarkan password
        np.random.seed(self.seed)
        np.random.shuffle(all_coeffs)
        
        # Embed message bits
        for bit_idx, bit in enumerate(message_bits):
            if bit_idx < len(all_coeffs):
                coeff_info = all_coeffs[bit_idx]
                original_coeff = coeff_info[0]
                modified_coeff = self._embed_bit_in_coeff(original_coeff, bit)
                all_coeffs[bit_idx][0] = modified_coeff
        
        # Reconstruct image
        modified_green = green_channel.copy()
        
        # Group coefficients back by block position
        block_coeffs = {}
        for coeff_info in all_coeffs[:len(message_bits)]:
            _, i, j, k = coeff_info
            if (i, j) not in block_coeffs:
                # Reconstruct original block
                orig_block = green_channel[i*8:(i+1)*8, j*8:(j+1)*8]
                block_coeffs[(i, j)] = dct(dct(orig_block.T, norm='ortho').T, norm='ortho').flatten()
            
            # Update coefficient
            block_coeffs[(i, j)][k] = coeff_info[0]
        
        # Apply modified coefficients back to image
        for (i, j), coeffs in block_coeffs.items():
            # Reshape and inverse DCT
            dct_block = coeffs.reshape(8, 8)
            reconstructed_block = idct(idct(dct_block.T, norm='ortho').T, norm='ortho')
            modified_green[i*8:(i+1)*8, j*8:(j+1)*8] = reconstructed_block
        
        # Clamp values dan gabungkan kembali
        modified_green = np.clip(modified_green, 0, 255)
        result_array = img_array.copy()
        result_array[:, :, 1] = modified_green
        
        # Pastikan result_array memiliki shape yang benar (H, W, 3)
        if result_array.shape[2] != 3:
            result_array = result_array[:, :, :3]
        
        return Image.fromarray(result_array.astype(np.uint8))
    
    def extract_message(self, stego_image):
        """Extract pesan dari stego image"""
        # Konversi ke RGB dan pastikan hanya 3 channels
        if stego_image.mode == 'RGBA':
            # Untuk RGBA, convert ke RGB dengan background putih  
            background = Image.new('RGB', stego_image.size, (255, 255, 255))
            background.paste(stego_image, mask=stego_image.split()[-1])
            stego_image = background
        elif stego_image.mode != 'RGB':
            stego_image = stego_image.convert('RGB')
            
        # Double check: pastikan gambar benar-benar RGB
        if stego_image.mode != 'RGB':
            stego_image = stego_image.convert('RGB')
        
        # Konversi ke array numpy dan pastikan shape (H, W, 3)
        img_array = np.array(stego_image, dtype=np.float32)
        if len(img_array.shape) != 3 or img_array.shape[2] != 3:
            raise ValueError(f"Error: Gambar harus RGB. Shape saat ini: {img_array.shape}")
        
        # Ambil channel hijau
        green_channel = img_array[:, :, 1]
        
        # Bagi gambar menjadi blok 8x8 untuk DCT
        h, w = green_channel.shape
        h_blocks = h // 8
        w_blocks = w // 8
        
        # Collect all DCT coefficients (sama seperti saat embed)
        all_coeffs = []
        
        for i in range(h_blocks):
            for j in range(w_blocks):
                block = green_channel[i*8:(i+1)*8, j*8:(j+1)*8]
                dct_block = dct(dct(block.T, norm='ortho').T, norm='ortho')
                
                # Flatten block
                flat_block = dct_block.flatten()
                for k, coeff in enumerate(flat_block):
                    if k != 0 and abs(coeff) > 0.5:  # Skip DC dan koefisien kecil
                        all_coeffs.append(coeff)
        
        # Shuffle dengan seed yang sama
        np.random.seed(self.seed)
        indices = list(range(len(all_coeffs)))
        np.random.shuffle(indices)
        
        # Extract bits
        extracted_bits = []
        for i in indices:
            if i < len(all_coeffs):
                bit = self._extract_bit_from_coeff(all_coeffs[i])
                extracted_bits.append(bit)
                
                # Stop setelah membaca length header dan message
                if len(extracted_bits) >= 32:  # Sudah ada length header
                    # Parse length
                    length = 0
                    for j in range(32):
                        length = (length << 1) | extracted_bits[j]
                    
                    if length > 0 and length <= 1000:  # Reasonable message length
                        total_bits_needed = 32 + (length * 8)
                        if len(extracted_bits) >= total_bits_needed:
                            break
                
                # Safety limit
                if len(extracted_bits) >= 10000:
                    break
        
        # Konversi bits ke string
        message = self._bits_to_string(extracted_bits)
        return message

def main():
    st.set_page_config(
        page_title="F5 Steganography",
        page_icon="🔐",
        layout="wide"
    )
    
    st.title("🔐 F5 Steganography Online")
    st.markdown("**Sembunyikan pesan rahasia dalam gambar menggunakan algoritma F5**")
    
    # Sidebar untuk password
    st.sidebar.header("🔑 Konfigurasi")
    password = st.sidebar.text_input("Password", value="mysecretkey", type="password")
    
    if not password:
        st.error("❌ Password tidak boleh kosong!")
        return
    
    # Inisialisasi F5
    f5 = F5Steganography(password)
    
    # Tab untuk Embed dan Extract
    tab1, tab2, tab3 = st.tabs(["📝 Embed Message", "🔍 Extract Message", "ℹ️ Info"])
    
    with tab1:
        st.header("Sembunyikan Pesan")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Upload Gambar")
            uploaded_file = st.file_uploader(
                "Pilih gambar", 
                type=['png', 'jpg', 'jpeg'],
                key="embed_upload"
            )
            
            if uploaded_file:
                # Baca dan konversi gambar ke RGB dari awal
                image = Image.open(uploaded_file)
                
                # Konversi ke RGB jika diperlukan
                if image.mode == 'RGBA':
                    # Untuk RGBA, convert ke RGB dengan background putih
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1])
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                st.image(image, caption="Gambar Asli", use_container_width=True)
                
                # Info gambar dan kapasitas
                width, height = image.size
                channels = len(image.getbands())
                mode = image.mode
                blocks = (width // 8) * (height // 8)
                capacity = blocks * 50 // 8  # Conservative estimate
                st.info(f"📏 Ukuran: {width} x {height} pixels\n🎨 Mode: {mode} ({channels} channels)\n📦 Kapasitas: ~{capacity} karakter")
        
        with col2:
            st.subheader("Pesan Rahasia")
            message = st.text_area(
                "Masukkan pesan yang ingin disembunyikan",
                height=150,
                placeholder="Ketik pesan rahasia di sini...",
                max_chars=500
            )
            
            if message:
                st.info(f"📝 Panjang pesan: {len(message)} karakter")
                if len(message) > 100:
                    st.warning("⚠️ Pesan panjang mungkin memerlukan gambar yang lebih besar")
        
        if st.button("🔐 Embed Pesan", type="primary"):
            if uploaded_file and message:
                try:
                    with st.spinner("Menyembunyikan pesan..."):
                        stego_image = f5.embed_message(image, message)
                    
                    st.success("✅ Pesan berhasil disembunyikan!")
                    
                    # Tampilkan hasil
                    col1, col2 = st.columns([1, 1])
                    
                    with col1:
                        st.subheader("Gambar Asli")
                        st.image(image, use_container_width=True)
                    
                    with col2:
                        st.subheader("Stego Image")
                        st.image(stego_image, use_container_width=True)
                    
                    # Analisis perubahan
                    orig_array = np.array(image)
                    stego_array = np.array(stego_image)
                    mse = np.mean((orig_array.astype(float) - stego_array.astype(float)) ** 2)
                    
                    if mse > 0:
                        psnr = 10 * np.log10(255**2 / mse)
                        st.info(f"📊 PSNR: {psnr:.2f} dB (Higher is better)")
                    
                    # Download button
                    buf = io.BytesIO()
                    stego_image.save(buf, format='PNG')
                    buf.seek(0)
                    
                    st.download_button(
                        label="💾 Download Stego Image",
                        data=buf.getvalue(),
                        file_name=f"stego_{uploaded_file.name.split('.')[0]}.png",
                        mime="image/png"
                    )
                    
                    # Store in session state for testing
                    st.session_state.test_image = stego_image
                    st.session_state.test_message = message
                    
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
            else:
                st.warning("⚠️ Silakan upload gambar dan masukkan pesan!")
    
    with tab2:
        st.header("Extract Pesan")
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("Upload Stego Image")
            stego_file = st.file_uploader(
                "Pilih stego image", 
                type=['png', 'jpg', 'jpeg'],
                key="extract_upload"
            )
            
            # Test button untuk debugging
            if 'test_image' in st.session_state:
                if st.button("🧪 Test dengan gambar yang baru di-embed"):
                    stego_file = "test_image"
            
            if stego_file:
                if stego_file == "test_image":
                    stego_image = st.session_state.test_image
                    st.image(stego_image, caption="Test Stego Image", use_container_width=True)
                else:
                    stego_image = Image.open(stego_file)
                    # Konversi ke RGB jika diperlukan untuk display
                    if stego_image.mode == 'RGBA':
                        background = Image.new('RGB', stego_image.size, (255, 255, 255))
                        background.paste(stego_image, mask=stego_image.split()[-1])
                        display_image = background
                    elif stego_image.mode != 'RGB':
                        display_image = stego_image.convert('RGB')
                    else:
                        display_image = stego_image
                    st.image(display_image, caption="Stego Image", use_container_width=True)
        
        with col2:
            if st.button("🔍 Extract Pesan", type="primary"):
                if stego_file or 'test_image' in st.session_state:
                    try:
                        with st.spinner("Mengekstrak pesan..."):
                            if stego_file == "test_image":
                                extracted_message = f5.extract_message(st.session_state.test_image)
                            else:
                                extracted_message = f5.extract_message(stego_image)
                        
                        if extracted_message and extracted_message.strip():
                            st.success("✅ Pesan berhasil diekstrak!")
                            st.subheader("Pesan Rahasia:")
                            st.text_area(
                                "Hasil ekstraksi",
                                value=extracted_message,
                                height=150,
                                disabled=True
                            )
                            
                            # Verification jika ada test message
                            if 'test_message' in st.session_state:
                                if extracted_message == st.session_state.test_message:
                                    st.success("✅ Verifikasi: Pesan cocok dengan yang di-embed!")
                                else:
                                    st.error("❌ Verifikasi: Pesan tidak cocok!")
                                    st.write("Original:", st.session_state.test_message)
                                    st.write("Extracted:", extracted_message)
                            
                        else:
                            st.warning("⚠️ Tidak ada pesan yang ditemukan atau password salah")
                            st.info("Pastikan:\n- Password sama dengan saat embed\n- File adalah stego image yang valid\n- Gambar tidak mengalami kompresi berlebihan")
                            
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        st.info("Debug: Pastikan gambar dan password benar")
                else:
                    st.warning("⚠️ Silakan upload stego image!")
    
    with tab3:
        st.header("ℹ️ Informasi F5 Steganography")
        
        st.markdown("""
        ### 🔧 Cara Kerja Algoritma F5
        
        **F5** adalah algoritma steganografi yang bekerja pada domain DCT (Discrete Cosine Transform):
        
        1. **DCT Transform**: Gambar dibagi menjadi blok 8x8 dan ditransformasi ke domain frekuensi
        2. **Coefficient Selection**: Pilih koefisien non-DC yang cukup besar
        3. **Permutation**: Acak urutan koefisien berdasarkan password  
        4. **Matrix Embedding**: Modifikasi LSB koefisien untuk embed data
        5. **Shrinkage**: Jika koefisien bernilai 1, ubah menjadi 0 untuk menghindari deteksi
        
        ### 🛡️ Keunggulan
        - **Invisible**: Tidak terdeteksi oleh mata manusia
        - **Secure**: Dilindungi password
        - **Robust**: Tahan terhadap kompresi ringan
        - **Efficient**: Kapasitas embedding yang baik
        
        ### 📋 Tips Penggunaan
        - Gunakan gambar berukuran minimal 256x256 pixels untuk pesan pendek
        - Gambar besar (>800x600) untuk pesan panjang  
        - Password harus sama persis saat embed dan extract
        - Mendukung format PNG, JPG, JPEG (termasuk RGBA)
        - Simpan hasil dalam format PNG untuk kualitas terbaik
        - Hindari kompresi JPEG berulang kali
        - Pesan maksimal bergantung ukuran gambar
        
        ### ⚠️ Batasan
        - Gambar kecil = kapasitas terbatas
        - Kompresi berlebihan dapat merusak data
        - Password case-sensitive
        - Gambar dengan noise tinggi kurang ideal
        """)

if __name__ == "__main__":
    main()