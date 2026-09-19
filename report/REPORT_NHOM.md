# Báo Cáo Nhóm — Lab 7: Embedding & Vector Store

**Nhóm:** DDCC  
**Thành viên:** Nguyễn Đức Danh, Bùi Gia Chính, Lê Phan Việt Cường, Nguyễn Quang Duy

> **Nộp 1 bản / nhóm.** Phần cá nhân (hướng tiếp cận, kết quả riêng, dự đoán…) mỗi thành viên nộp riêng trong
> `REPORT_CANHAN.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần nhóm: 40** = Lựa chọn tài liệu (10) + Thiết kế chiến lược (15) + Chất lượng truy xuất (10) + Thuyết
trình (5).

---

## 1. Lựa chọn tài liệu (Document Set Quality) — Nhóm (10 điểm)

### Chủ đề (Domain) & Lý Do Chọn

**Chủ đề:** Georgetown University Library Policies & Services — quy định mượn tài liệu, course reserves, media, thiết
bị, interlibrary loan và quy định sử dụng thư viện.

**Tại sao nhóm chọn chủ đề này?**

Corpus tập trung vào một domain thống nhất nhưng có nhiều loại dịch vụ và nhiều nhóm người dùng (`student`, `faculty`,
`all`). Đặc biệt, chính sách mượn sách và course reserves có thông tin khác nhau theo đối tượng, phù hợp để đánh giá tác
động của metadata filtering và so sánh các chiến lược chunking trên cùng một corpus.

### Danh sách tài liệu (Data Inventory)

| # | Tên tài liệu                             | Nguồn (Source URL)                                                | Ngày lấy / Phiên bản    | Số ký tự sau clean | Metadata đã gán                                                                     |
|---|------------------------------------------|-------------------------------------------------------------------|-------------------------|-------------------:|-------------------------------------------------------------------------------------|
| 1 | Borrowing Books - Faculty                | https://library.georgetown.edu/policies/borrowing/materials/books | 2026-09-19 / not-stated |                287 | `audience=faculty`, `department=library`, `category=borrowing`, `language=en`       |
| 2 | Borrowing Books - Undergraduate Students | https://library.georgetown.edu/policies/borrowing/materials/books | 2026-09-19 / not-stated |                174 | `audience=student`, `department=library`, `category=borrowing`, `language=en`       |
| 3 | Borrowing Media                          | https://library.georgetown.edu/policies/borrowing/materials/media | 2026-09-19 / not-stated |               1192 | `audience=all`, `department=library`, `category=borrowing-media`, `language=en`     |
| 4 | Course Reserves Information for Faculty  | https://library.georgetown.edu/course-reserves/faculty            | 2026-09-19 / not-stated |               3971 | `audience=faculty`, `department=library`, `category=course-reserves`, `language=en` |
| 5 | Course Reserves Information for Students | https://library.georgetown.edu/course-reserves/students           | 2026-09-19 / not-stated |               1818 | `audience=student`, `department=library`, `category=course-reserves`, `language=en` |
| 6 | Equipment Loans                          | https://library.georgetown.edu/equipment                          | 2026-09-19 / not-stated |               2259 | `audience=all`, `department=library`, `category=equipment`, `language=en`           |
| 7 | Interlibrary and Consortium Loans        | https://library.georgetown.edu/loans                              | 2026-09-19 / not-stated |               3211 | `audience=all`, `department=library`, `category=interlibrary-loan`, `language=en`   |
| 8 | Library Use Policies                     | https://library.georgetown.edu/policies/library-use               | 2026-09-19 / not-stated |               2110 | `audience=all`, `department=library`, `category=library-use`, `language=en`         |

**Cách chuẩn hóa corpus**

- Hai tài liệu borrowing được tách theo audience từ cùng trang nguồn: `borrowing-books-undergraduate.md` chỉ giữ quy
  định dành cho undergraduate students; `borrowing-books-faculty.md` chỉ giữ các nhóm faculty.
- Các heading, bảng và danh sách được chuẩn hóa về Markdown để giảm nhiễu retrieval; menu, site title lặp, form artifact
  và navigation text đã được loại bỏ.
- Nội dung nguồn, số liệu, thời hạn và quy định được giữ theo tài liệu crawl; không tự tạo `document_version` khi nguồn
  không công bố.
- Mọi file dùng UTF-8, `doc_id` trùng với filename stem, và `sources.csv` giữ provenance 1-1.

**Danh sách kiểm tra quản trị dữ liệu (Data governance checklist):**

- [x] Corpus có 8 tài liệu, nằm trong yêu cầu 5–10 tài liệu.
- [x] Các URL đã được crawler kiểm `robots.txt`; lượt crawl hoàn tất 8 saved, 0 skipped.
- [x] Corpus chỉ dùng nguồn công khai của Georgetown University Library.
- [x] Mỗi tài liệu có `doc_id`, `title`, `source_url`, `retrieved_at`, `document_version`, `audience`.
- [x] Mỗi tài liệu có thêm `department`, `category`, `language`.
- [x] `sources.csv` khớp 1-1 với 8 file `.md`.
- [x] `audience` có ít nhất hai giá trị khác nhau: `student`, `faculty`, `all`.
- [x] Các tài liệu đã được clean trước khi benchmark.

### Cấu trúc Metadata (Metadata Schema)

| Trường metadata    | Kiểu               | Ví dụ giá trị                                                       | Tại sao hữu ích cho retrieval?                                                           |
|--------------------|--------------------|---------------------------------------------------------------------|------------------------------------------------------------------------------------------|
| `doc_id`           | `str`              | `borrowing-books-undergraduate`                                     | ID ổn định của document gốc; dùng để trace chunk và xóa toàn bộ chunks của một document. |
| `title`            | `str`              | `Borrowing Books - Undergraduate Students`                          | Giữ ngữ cảnh và giúp đọc/trace kết quả retrieval.                                        |
| `source_url`       | `str`              | `https://library.georgetown.edu/policies/borrowing/materials/books` | Provenance: truy vết kết quả về trang nguồn.                                             |
| `retrieved_at`     | `str (YYYY-MM-DD)` | `2026-09-19`                                                        | Ghi thời điểm thu thập corpus.                                                           |
| `document_version` | `str`              | `not-stated`                                                        | Theo dõi phiên bản nếu nguồn có nêu; dùng `not-stated` khi nguồn không công bố.          |
| `audience`         | `str`              | `student`, `faculty`, `all`                                         | Field filter bắt buộc của L3A; giúp lọc đúng nhóm người dùng trước similarity search.    |
| `department`       | `str`              | `library`                                                           | Xác định domain/đơn vị sở hữu chính sách.                                                |
| `category`         | `str`              | `borrowing`, `course-reserves`, `equipment`                         | Phân loại dịch vụ/chính sách và có thể dùng làm chiều filter bổ sung.                    |
| `language`         | `str`              | `en`                                                                | Theo dõi ngôn ngữ corpus và lựa chọn embedding phù hợp.                                  |

---

## 2. Thiết kế chiến lược (Strategy Design) — Nhóm (15 điểm)

> Mỗi thành viên thử **một chiến lược khác nhau** trên cùng bộ tài liệu; nhóm tổng hợp và so sánh ở đây.

### Phân tích đường cơ sở (Baseline Analysis)

| Tài liệu | Chiến lược (Strategy)            | Số lượng Chunk | Độ dài trung bình | Giữ được ngữ cảnh không? |
|----------|----------------------------------|---------------:|------------------:|--------------------------|
|          | FixedSizeChunker (`fixed_size`)  |                |                   |                          |
|          | SentenceChunker (`by_sentences`) |                |                   |                          |
|          | RecursiveChunker (`recursive`)   |                |                   |                          |

### Chiến lược của từng thành viên

**Nguyễn Đức Danh**

- **Loại chiến lược:** [chốt ở CP5]
- **Mô tả & lý do chọn:** [CP5]

**Bùi Gia Chính**

- **Loại chiến lược:** [CP5]
- **Mô tả & lý do chọn:** [CP5]

**Lê Phan Việt Cường**

- **Loại chiến lược:** [CP5]
- **Mô tả & lý do chọn:** [CP5]

**Nguyễn Quang Duy**

- **Loại chiến lược:** [CP5]
- **Mô tả & lý do chọn:** [CP5]

### So Sánh Giữa Các Thành Viên

| Thành viên | Chiến lược (Strategy) | Điểm truy xuất (/10) | Điểm mạnh | Điểm yếu |
|------------|-----------------------|---------------------:|-----------|----------|
|            |                       |                      |           |          |
|            |                       |                      |           |          |
|            |                       |                      |           |          |
|            |                       |                      |           |          |

**Chiến lược nào tốt nhất cho chủ đề này? Tại sao?**

> [Điền sau CP6, dựa trên kết quả benchmark thực tế.]

---

## 3. Câu hỏi đánh giá & Chất lượng truy xuất (Retrieval Quality) — Nhóm (10 điểm)

### Câu hỏi đánh giá & Câu trả lời chuẩn (nhóm thống nhất)

> **Đúng 5 câu hỏi**, đa dạng, có thể kiểm chứng; **ít nhất 1 câu** cần lọc metadata mới trả lời tốt. Đây là bộ câu hỏi chung cho mọi thành viên chạy.

| # | Câu hỏi (Query) | Câu trả lời chuẩn (Gold Answer) | Chunk nào chứa thông tin? |
|---|-----------------|---------------------------------|---------------------------|
| 1 |                 |                                 |                           |
| 2 |                 |                                 |                           |
| 3 |                 |                                 |                           |
| 4 |                 |                                 |                           |
| 5 |                 |                                 |                           |

### Tổng hợp chất lượng truy xuất của nhóm

| # | Câu hỏi | Chiến lược tốt nhất cho câu này | Có chunk liên quan trong top-3? | Ghi chú |
|---|---------|---------------------------------|---------------------------------|---------|
| 1 |         |                                 |                                 |         |
| 2 |         |                                 |                                 |         |
| 3 |         |                                 |                                 |         |
| 4 |         |                                 |                                 |         |
| 5 |         |                                 |                                 |         |

**Lọc bằng metadata có giúp ích không? Ở câu hỏi nào?**
> *Viết 2-3 câu:*

---

## 4. Thuyết trình (Demo) & Bài học nhóm — Nhóm (5 điểm)

**Những phân tích (insights) hay nhất nhóm sẽ trình bày:**

> [Điền sau CP6.]

**Bài học rút ra khi so sánh trong nhóm:**

> [Điền sau CP6.]

**Nếu làm lại, nhóm sẽ thay đổi gì trong chiến lược dữ liệu (data strategy)?**

> [Điền sau CP6.]

---

## Tự Đánh Giá (Phần Nhóm)

| Tiêu chí                                 | Điểm tự đánh giá |
|------------------------------------------|-----------------:|
| Lựa chọn tài liệu (Document Set Quality) |             / 10 |
| Thiết kế chiến lược (Strategy Design)    |             / 15 |
| Chất lượng truy xuất (Retrieval Quality) |             / 10 |
| Thuyết trình (Demo)                      |              / 5 |
| **Tổng phần nhóm**                       |         **/ 40** |
