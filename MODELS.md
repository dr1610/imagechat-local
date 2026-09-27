# 必要モデル・Node

モデルは同梱しません。公式配布ページの条件を確認して取得します。

公式ComfyUI形式: https://huggingface.co/Comfy-Org/Qwen-Image-2.1

|用途|ファイル|ComfyUI内の配置|
|---|---|---|
|画像生成モデル|qwen_image_2.1_int8_convrot.safetensors|models/diffusion_models/|
|画像・指示Encoder|qwen3vl_8b_int8_convrot.safetensors|models/text_encoders/|
|VAE|qwen_image_2.1_vae_bf16.safetensors|models/vae/|
|編集Enhancer（任意）|qwen3.5_9b_qwen_image_2.1_pe_i2i.int8_convrot.safetensors|models/text_encoders/|
|新規Enhancer（任意）|qwen3.5_9b_qwen_image_2.1_pe_t2i.int8_convrot.safetensors|models/text_encoders/|

基本WorkflowはUNETLoader、CLIPLoader、VAELoader、TextEncodeQwenImage21、KSampler、LoadImage、SaveImage等を使用します。Qwen 2.1対応のComfyUIが必要です。
EnhancerはTextGenerate、BatchImagesNode、PreviewAnyも使用します。
Mask／Poseは追加でQwen-Image-2.1-Fun-Controlnet-Union.safetensorsとModelPatchLoader、QwenImage21FunControlNetApply、LoadImageMaskを使用します。モデルはComfyUIのmodels/model_patchesへ配置します。利用中のComfyUIの対応状況と提供元の条件を確認してください。

利用可能Nodeは接続先の `/object_info` から検査されます。生成停止は `/api/jobs/{prompt_id}/cancel` 対応が必要です。単にComfyUIが起動するだけでは全機能の互換性を保証しません。

既存のモデル保存場所を変更する必要はありません。ComfyUIの追加モデルパス設定も利用できます。bf16等を使う場合は接続設定とモデル選択を変更してください。自動選択は上記int8モデル名を使用します。

NoctQ / Turbo8等の取得先はpublic/model-catalog.jsonのsourceを参照。パッケージはモデル本体を再配布せず、そのライセンス適合性を保証しません。
