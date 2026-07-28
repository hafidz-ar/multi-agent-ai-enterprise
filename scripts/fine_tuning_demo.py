import os
import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import LoraConfig, get_peft_model, TaskType

def main():
    print("=== Demo Fine-Tuning Multi-Agent Parfum AI (LoRA) ===")
    
    # 1. Dataset Simulation
    # Di lingkungan nyata, data ini diambil dari log percakapan user atau database pengetahuan
    data = [
        {"text": "<User> Berapa stok YSL Est Aqua? <System> Stok YSL Est Aqua saat ini adalah 25 botol di Gudang A."},
        {"text": "<User> Tolong buatkan laporan penjualan bulan Mei. <System> Berikut adalah laporan penjualan bulan Mei: Total pendapatan Rp 150.000.000 dari 500 transaksi."},
        {"text": "<User> Apakah ada promo untuk parfum Chanel? <System> Ya, saat ini ada diskon 15% untuk parfum Chanel khusus pembelian offline."},
        {"text": "<User> Pesan 2 botol Bvlgari Man. <System> Pesanan 2 botol Bvlgari Man telah dibuat dengan nomor pesanan #ORD-2023. Silakan lakukan pembayaran."},
        {"text": "<User> Bagaimana status produksi batch 004? <System> Batch 004 sedang dalam tahap pengemasan (packaging) dan diperkirakan selesai besok."}
    ]
    
    print(f"Loading {len(data)} samples for fine-tuning...")
    dataset = Dataset.from_list(data)
    
    # 2. Model & Tokenizer
    # Menggunakan model kecil untuk simulasi demo
    model_name = "distilgpt2" 
    print(f"Loading base model: {model_name}")
    
    # Inisialisasi Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.pad_token = tokenizer.eos_token
    
    def tokenize_function(examples):
        return tokenizer(examples["text"], padding="max_length", truncation=True, max_length=64)
    
    tokenized_dataset = dataset.map(tokenize_function, batched=True)
    
    # Inisialisasi Model
    model = AutoModelForCausalLM.from_pretrained(model_name)
    
    # 3. LoRA Configuration
    print("Configuring LoRA (Low-Rank Adaptation)...")
    peft_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        inference_mode=False,
        r=8,  # rank
        lora_alpha=32,
        lora_dropout=0.1,
        # distilgpt2 menggunakan c_attn, c_proj untuk attention
        target_modules=["c_attn"] 
    )
    
    # Wrap model dengan PEFT
    peft_model = get_peft_model(model, peft_config)
    peft_model.print_trainable_parameters()
    
    # 4. Training Arguments
    training_args = TrainingArguments(
        output_dir="./models/fine_tuned_parfum_ai",
        per_device_train_batch_size=2,
        num_train_epochs=3, # Cukup 3 epoch untuk simulasi
        logging_steps=1,
        learning_rate=2e-4,
        save_strategy="no", # Matikan save untuk sekadar demo
        report_to="none"    # Matikan wandb/dll
    )
    
    data_collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)
    
    # 5. Trainer
    trainer = Trainer(
        model=peft_model,
        args=training_args,
        train_dataset=tokenized_dataset,
        data_collator=data_collator,
    )
    
    # 6. Jalankan Training
    print("\nStarting Training...")
    try:
        trainer.train()
        print("\nTraining Completed Successfully!")
        print("Model LoRA weights saved (simulated) to ./models/fine_tuned_parfum_ai")
    except Exception as e:
        print(f"Training failed: {str(e)}")

if __name__ == "__main__":
    main()
