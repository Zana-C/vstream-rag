Below is the professional `CLAUDE.md` guide for the VisionStream AI project, structured to be compatible with Anthropic-style skills and modular development.

---

# CLAUDE.md

## Project Vision: VisionStream AI

VisionStream AI is an intelligent system designed to transform passive video recordings into searchable, structured knowledge bases. It accomplishes this by detecting slide transitions, deduplicating frames, and extracting contextual information for LLM interaction.

## Team and Roles

* **Team Name:** VisionStream AI


* **Team Leader:** İsmail Erdem Aydoğan


* **Members:** İsmail Erdem Aydoğan (ID: 230209039), Zana Çiftçi (ID: 230209072)


* **Course:** Large Language Models



## Directory Structure

```text
/project-root
├── CLAUDE.md                # Project orchestration and standards
├── project_description.md   # Detailed project roadmap and objectives
├── skills/                  # Core functional tools (Anthropic-style)
│   ├── vision_utils.py      # Frame extraction and transition detection
│   ├── deduplication.py     # SSIM and Image Hashing logic
│   ├── text_analysis.py     # OCR and diagram processing
│   └── agent_logic.py       # LLM orchestration and RAG workflow
├── src/                     # Application entry points
└── tests/                   # Validation for skills and core logic

```

## Technical Standards

### 1. Development Principles

* **Modular Skills:** All core logic must reside in the `skills/` directory as reusable tools.


* **Error Handling:** Vision-related skills must handle noise and camera movement using advanced deduplication logic.


* **Multimodal Focus:** The system must process both text and visual elements (charts/diagrams) to provide deep context to the LLM.



### 2. Core Methodologies

* **Computer Vision:** Utilize frame-by-frame analysis and change detection.


* **Deduplication:** Implement image hashing and structural similarity metrics.


* **Contextual Analysis:** Map slides to specific timestamps to allow the LLM to navigate the original video.



## Build and Commands

### Environment Setup

* Required: Python 3.10+
* Key Libraries: OpenCV, Scikit-Image, Tesseract/EasyOCR, LangChain.

### Common Tasks

* **Run Extraction:** `python src/main.py --source <video_path>`
* **Run Tests:** `pytest tests/`
* **Linting:** `flake8 skills/ src/`

## Implementation Roadmap

1. **Detection:** Implement slide transition detection in `vision_utils.py`.


2. **Filtering:** Apply deduplication logic to eliminate redundant frames and noise.


3. **Extraction:** Use OCR and visual analysis to feed data into the LLM environment.


4. **Interaction:** Enable natural language querying of the processed presentation content.