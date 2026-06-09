"""
V3.5 Hybrid OCR Correction Pipeline
-----------------------------------
Bu modül, ekran yansımaları ve düşük çözünürlük sebebiyle EasyOCR'dan bozuk çıkan
metinleri, yerel bir LLM'in dil yeteneklerini ve Structured Output (Yapılandırılmış Çıktı)
mimarisini kullanarak temizler ve garantili bir JSON/Dict formatında döndürür.
"""

from pydantic import BaseModel, Field
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

# 1. Pydantic Şeması (Veri formatını kilitler)
class CleanedSlideData(BaseModel):
    question_id: str = Field(description="Sorunun numarası veya başlığı (örn: Question 8)")
    question_text: str = Field(description="Yazım hataları düzeltilmiş, net soru kökü metni")
    option_A: Optional[str] = Field(description="A şıkkının düzeltilmiş metni (A harfi ve parantez olmadan)")
    option_B: Optional[str] = Field(description="B şıkkının düzeltilmiş metni (B harfi ve parantez olmadan)")
    option_C: Optional[str] = Field(description="C şıkkının düzeltilmiş metni (C harfi ve parantez olmadan)")
    option_D: Optional[str] = Field(description="D şıkkının düzeltilmiş metni (D harfi ve parantez olmadan)")
    option_E: Optional[str] = Field(description="Varsa E şıkkının düzeltilmiş metni, yoksa null")


# 2. Sistem İstemi (Modelin sınırlarını çizer)
ocr_correction_prompt = ChatPromptTemplate.from_messages([
    ("system", """Sen uzman bir Veri Temizleme (Data Cleansing) asistanısın.
Görevin, yansıma ve düşük çözünürlük nedeniyle OCR motorundan bozuk çıkmış çoktan seçmeli soru metinlerini onarmak ve yapılandırmaktır.

KATI KURALLAR:
1. Bağlamsal Onarım: Yanlış okunmuş kelimeleri cümle bağlamına göre İngilizce veya Türkçe olarak düzelt (örn: 'h0ldout' -> 'holdout', 'g3neralizati0n' -> 'generalization').
2. Sadakat: Metnin orijinal anlamını ASLA değiştirme. Soruyu cevaplamaya çalışma. Sadece olanı onar.
3. Ayrıştırma: Soru kökünü ve şıkları birbirinden net bir şekilde ayır.
4. Temizlik: Slayttaki konu dışı arayüz yazılarını (örn: 'Microsoft 365 Denemenizi Başlatın', 'Araçlar', 'Slayt Gösterisi') tamamen yoksay.
5. Format: Sadece ve sadece senden istenen JSON şemasına uygun yanıt ver. Ekstra hiçbir açıklama yapma."""),
    ("human", "İşte onarman ve yapılandırman gereken bozuk OCR metni:\n\n{raw_ocr_text}")
])


# 3. Çalıştırma Fonksiyonu (LCEL Zinciri)
def process_and_clean_ocr(raw_ocr_text: str, model_name: str = "qwen2.5:14b") -> dict:
    """
    EasyOCR'dan gelen bozuk metni alır, Ollama üzerinden LLM'e gönderir
    ve temizlenmiş bir dict olarak döndürür.
    """
    try:
        # LLM Tanımlaması (Temperature 0 = Maksimum kesinlik)
        llm = ChatOllama(model=model_name, temperature=0.0)
        
        # Pydantic şemasını LLM'e dayatıyoruz
        structured_llm = llm.with_structured_output(schema=CleanedSlideData)
        
        # Prompt ile modeli zincirliyoruz
        correction_chain = ocr_correction_prompt | structured_llm
        
        # Çalıştır ve sonucu al
        cleaned_result = correction_chain.invoke({"raw_ocr_text": raw_ocr_text})
        return cleaned_result.dict()
        
    except Exception as e:
        print(f"[!] OCR Düzeltme Hatası: {str(e)}")
        # API veya model çökerse, ham veriyi boş şablonla döndür (Sistemin çökmesini engeller)
        return {
            "question_id": "Unknown",
            "question_text": raw_ocr_text,
            "option_A": None, "option_B": None, "option_C": None, "option_D": None, "option_E": None
        }


# --- TEST KULLANIMI ---
if __name__ == "__main__":
    messy_text = "2=| 4 'Gv Donuştur Question 8 8. A h0ldout datas3t is ma1nly used to: A) Increas training data s1ze B) Tune hyperparam C) Estimate g3neralization performance"
    
    print("Bozuk metin işleniyor, lütfen bekleyin...")
    clean_data = process_and_clean_ocr(messy_text)
    
    import json
    print(json.dumps(clean_data, indent=2, ensure_ascii=False))
