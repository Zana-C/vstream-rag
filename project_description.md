# VisionStream AI - Project Description

## 1. Projenin Amacı ve Kapsamı
VisionStream AI, uzun ve statik video kayıtlarını (özellikle eğitim ve sunum videolarını) interaktif, aranabilir ve anlamlandırılabilir bilgi tabanlarına dönüştürmeyi amaçlayan akıllı bir video analiz sistemidir. 

Eğitim veya toplantı kayıtlarında kullanıcıların belirli bir konuyu, slaytı veya grafiği bulması oldukça zaman alıcıdır. Bu proje, sadece pasif izlemeyi ortadan kaldırıp, videoları Large Language Models (Büyük Dil Modelleri) ve RAG (Retrieval-Augmented Generation) altyapısı ile sohbet edilebilir bir deneyime dönüştürür.

## 2. Temel Hedefler
- **Zaman Tasarrufu:** Saatlerce süren video kayıtlarını analiz edip yalnızca önemli anları (örneğin yeni bir slayt geçişini) filtreleyerek özetlemek.
- **Akıllı Çıkarım (OCR & Vision):** Slaytların içeriğindeki metinleri ve temel bağlamı algılayıp metin (JSON) formatına dönüştürmek.
- **Etkileşimli Arama (RAG):** Kullanıcının doğal dille "X konusu ne zaman anlatıldı?" veya "Slayttaki son formül neydi?" gibi sorular sormasına olanak tanımak.
- **Esnek Altyapı:** Hem yerel olarak çalışan (Ollama / Qwen 2.5) hem de bulut tabanlı API'leri (OpenAI, Anthropic) destekleyebilen esnek bir LLM entegrasyonu sunmak.

## 3. Sistem Mimarisi
Projenin temel iş akışı dört aşamadan oluşur:

1. **Video İşleme ve Tespiti (Vision & Detection):**
   - Video kare kare işlenerek, görsel anlamda önemli değişiklikler (slayt geçişleri) tespit edilir.
2. **Filtreleme (Deduplication):**
   - SSIM veya Image Hashing algoritmaları ile birbirine çok benzeyen ve tekrar eden kareler filtrelenir. Sadece anlamlı değişikliğin olduğu kareler tutulur.
3. **Veri Çıkarımı (Extraction):**
   - Ayıklanan karelerden EasyOCR/Tesseract gibi araçlarla metinler çıkarılır. Bu metinler bağlamları ile birlikte yapılandırılmış bir JSON dosyasına kaydedilir.
4. **Etkileşim (Interaction & RAG):**
   - Elde edilen JSON formatındaki veriler ChromaDB (veya FAISS) gibi bir vektör veritabanına aktarılır. Kullanıcı Streamlit arayüzü üzerinden soru sorduğunda, LLM vektör veritabanından ilgili bağlamı getirerek doğru ve referanslı bir cevap üretir.

## 4. Kullanılacak Teknolojiler
- **Video İşleme:** OpenCV, scikit-image
- **OCR:** EasyOCR veya pytesseract
- **LLM Orkestrasyonu:** LangChain
- **Vektör Veritabanı:** ChromaDB / FAISS
- **Kullanıcı Arayüzü:** Streamlit
- **LLM Sağlayıcıları:** Ollama (Local Qwen 2.5 14B) veya Harici Servisler (OpenAI, vb.)

## 5. Yol Haritası (Roadmap)
- [ ] **Aşama 1: Çekirdek Becerilerin Kurulumu:** Dizin yapısının oluşturulması, bağımlılıkların eklenmesi. Video işleme ve OCR modüllerinin (`vision_utils.py`, `text_analysis.py`) kodlanması.
- [ ] **Aşama 2: RAG ve LLM Entegrasyonu:** Çıkarılan verilerin JSON'a aktarımı, vektör veritabanına eklenmesi ve LangChain üzerinden RAG zincirinin kurulması.
- [ ] **Aşama 3: Arayüz (UI) Geliştirme:** Streamlit ile video yükleme, LLM konfigürasyonu (Yerel vs API) ve sohbet ekranının tasarlanması.
- [ ] **Aşama 4: Test ve Optimizasyon:** Örnek videolarla testlerin yapılması, performans iyileştirmeleri (kare yakalama hızı, OCR doğruluğu) ve hataların giderilmesi.
