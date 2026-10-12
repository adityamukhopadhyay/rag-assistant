---
title: "Photogrammetry-AI (Glasses3D) — Product Images to 3D Models with Vision Analysis and Generative 3D"
slug: "photogrammetry-ai"
kind: "project"
site_slug: null
page_url: "https://github.com/adityamukhopadhyay/Photogrammetry-AI"
source: "public GitHub repository adityamukhopadhyay/Photogrammetry-AI, read 2026-10-08; personal / freelance-era project, January 2025"
summary: "A personal generative-3D pipeline: scrape an eyewear product page (Warby Parker), pull its images and specifications, run a detailed vision analysis of the frames, have DeepSeek-R1 turn specs plus visual analysis into a production-ready 3D-modelling prompt with PBR material values, and generate a downloadable GLB model through the FAL Hyper3D Rodin API. Includes CLAHE image enhancement, Pydantic schemas and retry logic."
---
# Photogrammetry-AI (Glasses3D) — Product Images to 3D Models with Vision Analysis and Generative 3D

## 1. Summary

Photogrammetry-AI, named Glasses3D inside the repository, is a personal project by Aditya Mukhopadhyay from January 2025 (github.com/adityamukhopadhyay/Photogrammetry-AI). It is an end-to-end pipeline that takes a glasses product page, collects the product's images and specifications, analyses the images for material, colour, branding, lens and hinge details, writes a precise 3D-modelling prompt from that analysis, and generates a 3D model of the glasses in GLB format through a generative-3D API. The goal was to automate 3D asset creation for e-commerce eyewear from the photos and text a retailer already has, without training a custom model.

It is a side project from Aditya's freelance period, not production work at Badho and not on his resume. It is relevant as evidence of computer-vision and vision-language work: image enhancement with OpenCV, multimodal analysis of product photos, prompt engineering for generative 3D, and an orchestrated multi-stage pipeline with validation and retries.

## 2. Tech Stack

- Language: Python (asyncio throughout).
- Scraping: Playwright (headless Chromium, `wait_until="networkidle"`) to render the product page, BeautifulSoup to parse it; Selenium with webdriver-manager for one browser-automation step (see 3.2).
- Language model: DeepSeek via its OpenAI-compatible API, model `deepseek-reasoner` (DeepSeek-R1), temperature 0.1, used for specification extraction and prompt assembly.
- Vision analysis: a long, structured vision instruction (materials, marbling, branding placement, lens tint and reflectivity, hinge type, measurements, PBR roughness values) run against the product images.
- Image processing: OpenCV, CLAHE contrast enhancement in LAB colour space (clip limit 3.0, 8×8 tiles), minimum resolution and aspect-ratio settings in `config/settings.yaml`.
- Generative 3D: FAL's Hyper3D Rodin model (`fal-ai/hyper3d/rodin`) through `fal_client.subscribe`, with quality "high", PBR material, GLB geometry, the "HighPack" add-on and hyper mode enabled; results downloaded as `model.glb`.
- Data validation: Pydantic models (for example `ProductSpecs` with fields such as frame material) for the scraped specifications; LangChain `Document` objects for the scraped HTML content; tenacity-style retries around API calls; YAML configuration; a logging config and a `logs/` directory.

## 3. How It Works

The repository is organised as `src/data_collection`, `src/image_processing`, `src/llm`, `src/prompt_engineering`, `src/rodin_integration` and `src/utils`, with `main.py` and `do_everything.py` as entry points that run the stages in order.

### 3.1 Data collection
`WarbyScraper` renders a Warby Parker product URL with Playwright, parses the HTML with BeautifulSoup, pulls the product thumbnail images (the `PDP Thumbnail Image N` elements) and wraps the page text in LangChain documents. The page content is then sent to the language model with a structured extraction prompt that asks for frame material, lens type and optical properties, measurements and similar fields while keeping the original material names, and the answer is validated against the Pydantic schema. The image URLs are saved for the next stages.

### 3.2 Vision analysis
The repository's `settings.yaml` configures up to four images per request, and `DeepSeekClient.ainvoke` accepts images and base64-encodes them. Because DeepSeek-R1 is a text model, the committed `main.py` obtains the detailed visual description through a separate image-description step: it drives a browser with Selenium, submits the product image URL, and captures the description, then feeds that description plus the long vision instruction into the pipeline as `vision_analysis.txt`. The vision instruction is specific: identify acetate versus titanium versus steel, describe marbling veins and layered acetate, locate the "WARBY PARKER" engraving on the left temple and its distance from the hinge, estimate lens tint gradient colours and transition sharpness, describe hinge type and screw heads, validate bridge width and temple length, and output PBR roughness values on a 0–1 scale, in millimetres, with left/right orientation.

### 3.3 Image enhancement
`ImageEnhancer.enhance` converts each downloaded image to LAB, applies CLAHE to the L channel (clip limit 3.0, tile grid 8×8) and converts back to BGR, writing `enhanced_<name>` to `data/processed_images`. This lifts local contrast so texture and marbling are easier to describe and model.

### 3.4 Prompt generation and validation
`PromptGenerator` fills a template with the extracted specifications, then calls `_validate_prompt`, which asks the model to combine the specifications and the visual analysis into one production-ready 3D-modelling prompt. The validation prompt is opinionated: output only the final prompt; begin with "Create a 3D model of a pair of glasses based on the given specifications and visual analysis"; include branding details such as etched text positioned a stated distance from the hinge; set lens colour intensity to 0.0 for transparent lenses and describe them as clear polycarbonate with anti-reflective coating; and keep the prompt simple enough for the 3D model to follow. A `ConfigGenerator` then turns the final prompt into the Rodin job configuration.

### 3.5 3D generation
`RodinAPI` validates that the configuration has a prompt and input image URLs, extracts optional `roughness` and `metallic` values from the prompt text (either `key=value` or `key: value`), and submits the job to `fal-ai/hyper3d/rodin` with the configured quality, material, tier, geometry format and add-ons. `ModelProcessor.process_product` submits the job, waits for the result, logs the returned model URL, downloads the GLB (checking the content type) and saves it to `data/3d_models/model.glb`.

## 4. Design Decisions

- **No custom model.** The README states the economic constraint plainly: training a bespoke image-to-3D model would be expensive, so the pipeline composes existing services (a reasoning LLM, an image-description step and a generative-3D API) and spends its effort on data quality and prompt precision.
- **Specs and vision are combined, not either alone.** Retail pages give exact measurements and material names but no texture detail; images give texture, colour and branding placement but unreliable dimensions. The validation step merges both so the 3D prompt is both measurable and visually faithful.
- **Explicit PBR values.** Asking the analysis for roughness and metallic values, and parsing them out of the final prompt for the Rodin call, gives the generator material parameters rather than adjectives.
- **Validation and retries.** Pydantic schemas on extracted specs and retry logic around the network calls keep a multi-stage, multi-vendor pipeline from failing silently.

## 5. Limitations (from the project's own README)

- Single- or two-view inputs: complex geometry such as curved lenses may not be reproduced exactly.
- Material ambiguity: one image cannot always tell shiny from matte from translucent.
- Dependence on third-party APIs (DeepSeek, FAL Rodin) and on the Warby Parker page structure for scraping.
- The committed code is a working prototype: some modules (`metadata_extractor.py`, `detail_validator.py`, `schema_validator.py`) are stubs, and parts of the flow are run from scripts rather than one CLI.

## 6. What It Demonstrates

- Computer-vision preprocessing (CLAHE in LAB space) chosen for a concrete downstream purpose.
- Vision-language analysis of product photos with a tightly specified rubric, and prompt engineering for a generative-3D model.
- Orchestrating scraping, LLM extraction, image processing and a 3D-generation API into one asynchronous pipeline with schemas, configuration files, logging and retries.
