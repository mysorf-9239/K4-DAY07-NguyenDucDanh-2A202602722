# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Nguyễn Đức Danh  
**Nhóm:** DDCC  
**Ngày:** 19/09/2026

> **Nộp 1 bản / sinh viên.** Phần nhóm (lựa chọn tài liệu, thiết kế chiến lược, bộ câu hỏi đánh giá, demo) nộp chung 1
> bản trong `REPORT_NHOM.md`. Chi tiết thang điểm: `docs/SCORING.md`.

**Tổng điểm phần cá nhân: 60** = Khởi động (5) + Hướng tiếp cận (10) + Hoàn thiện code (30) + Dự đoán độ tương tự (5) +
Kết quả truy xuất của tôi (10).

---

## 1. Khởi động (Warm-up) — Cá nhân (5 điểm)

### Độ tương tự Cosine (Cosine Similarity) (Bài tập 1.1)

**Độ tương tự cosine cao (High cosine similarity) nghĩa là gì?**

Độ tương tự cosine cao nghĩa là hai vector embedding có hướng gần nhau, cho thấy hai đoạn văn bản có nội dung hoặc ý
nghĩa ngữ nghĩa tương tự nhau. Hai câu không nhất thiết phải sử dụng cùng từ vựng để có cosine similarity cao nếu
embedding biểu diễn được ý nghĩa của chúng gần nhau.

**Ví dụ có độ tương tự CAO:**

* Câu A: `Sinh viên cần nộp học phí trước hạn.`
* Câu B: `Người học phải thanh toán học phí đúng thời hạn.`
* Tại sao tương đồng: Hai câu dùng từ ngữ khác nhau nhưng cùng diễn đạt yêu cầu thanh toán học phí đúng thời hạn.

**Ví dụ có độ tương tự THẤP:**

* Câu A: `Sinh viên được mượn sách trong sáu tuần.`
* Câu B: `Hôm nay trời có mưa lớn.`
* Tại sao khác: Hai câu nói về hai chủ đề và ngữ nghĩa gần như không liên quan.

**Tại sao độ tương tự cosine (cosine similarity) được ưu tiên hơn khoảng cách Euclid (Euclidean distance) cho text
embeddings?**

Cosine similarity tập trung vào **hướng** của hai vector thay vì khoảng cách tuyệt đối giữa chúng, nên phù hợp khi mục
tiêu là so sánh mức độ giống nhau về ngữ nghĩa. Euclidean distance bị ảnh hưởng nhiều hơn bởi magnitude của vector,
trong khi đối với text embeddings ta thường quan tâm hai vector có cùng hướng biểu diễn ý nghĩa hay không.

### Bài toán tính toán Chunking (Bài tập 1.2)

**Tài liệu 10,000 ký tự, `chunk_size=500`, `overlap=50`. Bao nhiêu chunks?**

Công thức:

```text
ceil((document_length - overlap) / (chunk_size - overlap))
```

Thay số:

```text
ceil((10000 - 50) / (500 - 50))
= ceil(9950 / 450)
= ceil(22.111...)
= 23
```

**Đáp án: 23 chunks.**

Kết quả này cũng được kiểm chứng bằng `FixedSizeChunker` có sẵn trong repo.

**Nếu độ chồng chéo (overlap) tăng lên 100, số lượng chunk thay đổi thế nào? Tại sao muốn độ chồng chéo nhiều hơn?**

Khi `overlap=100`:

```text
ceil((10000 - 100) / (500 - 100))
= ceil(9900 / 400)
= ceil(24.75)
= 25
```

Số lượng chunk tăng từ **23 lên 25**. Overlap lớn hơn làm tăng số chunk và chi phí lưu trữ/retrieval, nhưng giúp bảo
toàn ngữ cảnh tại biên giữa hai chunk. Thông tin nằm sát điểm cắt có cơ hội xuất hiện trong cả hai chunk, từ đó giảm
nguy cơ retrieval bỏ mất một mẩu thông tin quan trọng.

---

## 2. Hướng tiếp cận của tôi (My Approach) — Cá nhân (10 điểm)

### Các hàm chia nhỏ (Chunking Functions)

**`SentenceChunker.chunk` — hướng tiếp cận:**

Tôi sử dụng regular expression với positive lookbehind `(?<=[.!?])\s+` để tách tại khoảng trắng nằm sau dấu kết thúc
câu. Cách này giữ lại dấu câu thay vì làm mất `"."`, `"!"` hoặc `"?"`, sau đó các câu được strip và gom tối đa theo
`max_sentences_per_chunk`.

Một số edge case chưa được xử lý hoàn hảo là chữ viết tắt như `Dr.`, `TS.` hoặc các trường hợp dấu chấm không thực sự
đánh dấu kết thúc câu. Đây là giới hạn của phương pháp sentence splitting dựa trên regex đơn giản.

**`RecursiveChunker.chunk` / `_split` — hướng tiếp cận:**

Thuật toán thử các separator theo thứ tự ưu tiên:

```python
["\n\n", "\n", ". ", " ", ""]
```

Các boundary lớn như paragraph hoặc dòng được ưu tiên trước để giữ tính mạch lạc của nội dung. Nếu một phần sau khi
split vẫn lớn hơn `chunk_size`, `_split` tiếp tục đệ quy với separator nhỏ hơn.

Các base case gồm: text rỗng, text đã nhỏ hơn `chunk_size`, không còn separator, hoặc separator cuối cùng là chuỗi rỗng.
Khi không còn separator phù hợp, thuật toán fallback sang hard split theo số ký tự. Sau bước đệ quy, các đoạn nhỏ liền
kề được merge ngược trở lại đến gần `chunk_size` nhằm tránh sinh quá nhiều chunk vụn.

### Lớp EmbeddingStore

**`add_documents` + `search` — hướng tiếp cận:**

Tôi sử dụng in-memory store để phần lõi độc lập với ChromaDB và có hành vi ổn định giữa các môi trường. Mỗi `Document`
được chuẩn hóa thành một record gồm `id`, `content`, bản sao `metadata` và vector `embedding`; `add_documents` không tự
chunk vì chunking được thực hiện ở tầng ngoài trước khi ingest.

Khi search, query được embed bằng cùng `embedding_fn`, sau đó tính dot product với embedding của từng record. Vì các
embedding dùng trong lab đã được chuẩn hóa, dot product có thể dùng trực tiếp làm similarity score. Kết quả được sắp xếp
giảm dần theo score và giới hạn bởi `top_k`.

**`search_with_filter` + `delete_document` — hướng tiếp cận:**

Metadata filtering được thực hiện **trước similarity search** để các vị trí trong `top_k` chỉ được cạnh tranh bởi các
record thỏa điều kiện lọc. Nếu search trước rồi mới filter, các record sai metadata có thể chiếm hết top-k và làm mất
các kết quả hợp lệ.

`delete_document` xóa tất cả record có `metadata["doc_id"]` trùng với document gốc. `_make_record` sao chép metadata để
không mutate dữ liệu từ caller và dùng `setdefault("doc_id", doc.id)` để luôn có `doc_id` nhưng vẫn giữ nguyên `doc_id`
gốc nếu chunk đã được gán từ trước.

### Tác tử KnowledgeBaseAgent

**`answer` — hướng tiếp cận:**

Agent thực hiện pipeline **retrieve → construct context → call LLM**. Các chunk truy xuất được đánh số `[1]`, `[2]`,
`[3]` và gắn nguồn từ `source_url`, `source`, `doc_id` hoặc `id` để hỗ trợ source traceability.

Prompt yêu cầu model chỉ trả lời dựa trên context được cung cấp, không tự suy đoán khi thiếu thông tin và trích dẫn số
nguồn khi có thể. Nếu store không trả về kết quả, agent trả thông báo không tìm thấy thông tin thay vì gọi LLM khi không
có grounding.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử

Kết quả:

```text
collected 42 items

TestProjectStructure:
- test_root_main_entrypoint_exists PASSED
- test_src_package_exists PASSED

TestClassBasedInterfaces:
- test_chunker_classes_exist PASSED
- test_mock_embedder_exists PASSED

TestFixedSizeChunker:
- 7 tests PASSED

TestSentenceChunker:
- 4 tests PASSED

TestRecursiveChunker:
- 4 tests PASSED

TestEmbeddingStore:
- 8 tests PASSED

TestKnowledgeBaseAgent:
- 2 tests PASSED

TestComputeSimilarity:
- 4 tests PASSED

TestCompareChunkingStrategies:
- 3 tests PASSED

TestEmbeddingStoreSearchWithFilter:
- 3 tests PASSED

TestEmbeddingStoreDeleteDocument:
- 3 tests PASSED

42 passed in 0.03s
```

**Số lượng bài test vượt qua (pass): 42 / 42**

### Manual RAG Demo

Command:

```bash
python main.py "Chunking là gì?"
```

Kết quả chính:

```text
Loaded 5 documents
Embedding backend: mock embeddings fallback
Stored 5 documents in EmbeddingStore

=== EmbeddingStore Search Test ===
Query: Chunking là gì?
1. score=0.150 source=data/rag_system_design.md
2. score=0.027 source=data/python_intro.txt
3. score=0.025 source=data/chunking_experiment_report.md

=== KnowledgeBaseAgent Test ===
Question: Chunking là gì?
Agent answer:
[DEMO LLM] Generated answer from prompt preview: ...
```

`main.py` đã chạy end-to-end từ load file → embedding → vector store → retrieval → `KnowledgeBaseAgent`. File
`data/customer_support_playbook.txt` không tồn tại nên được bỏ qua đúng theo cơ chế xử lý missing file của demo. Backend
mock chỉ được dùng để kiểm tra pipeline và test logic; benchmark chất lượng retrieval ở giai đoạn sau sẽ cần embedding
có ngữ nghĩa.

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

Các dự đoán dưới đây được ghi trước khi chạy embedding/similarity experiment. Kết quả thực tế được đo bằng
`gemini-embedding-001`.

| Cặp | Câu A                                                | Câu B                                                            | Dự đoán          | Điểm thực tế | Đúng?                                  |
|-----|------------------------------------------------------|------------------------------------------------------------------|------------------|-------------:|----------------------------------------|
| 1   | `Students can borrow books for six weeks.`           | `Undergraduate learners may keep library books for six weeks.`   | Cao              |       0.8821 | Đúng                                   |
| 2   | `Faculty members can place books on course reserve.` | `Professors may request books for course reserves.`              | Cao              |       0.9015 | Đúng                                   |
| 3   | `Equipment must be reserved one day in advance.`     | `Library equipment reservations should be made ahead of pickup.` | Cao              |       0.8470 | Đúng                                   |
| 4   | `Interlibrary loans may take several business days.` | `Pizza is not permitted on most library floors.`                 | Thấp             |       0.5931 | Đúng tương đối — thấp nhất trong 5 cặp |
| 5   | `Students can borrow reserve items.`                 | `Faculty can choose reserve loan periods.`                       | Trung bình / Cao |       0.7875 | Đúng                                   |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**

Cặp 4 là kết quả đáng chú ý nhất: hai câu nói về hai nội dung rất khác nhau nhưng cosine similarity vẫn đạt `0.5931`.
Dù đây là điểm thấp nhất trong năm cặp, nó cho thấy embedding không chỉ phản ánh sự trùng khớp trực tiếp của từ khóa mà
còn có thể giữ một phần tín hiệu chung về domain và kiểu nội dung chính sách thư viện.

Cặp 5 đạt `0.7875` dù hai câu nói về hai audience và hai hành động khác nhau. Điều này cho thấy embedding có thể đánh
trọng số khá lớn cho việc hai câu cùng thuộc domain `course reserves`/borrowing. Vì vậy, semantic similarity cao không
đồng nghĩa với hai câu có cùng đáp án chi tiết; metadata filtering và kiểm tra nội dung chunk vẫn cần thiết.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Nhóm thống nhất cùng một corpus, cùng 5 benchmark query và gold answer. Chiến lược cá nhân của tôi là **heading-aware
chunking kết hợp `RecursiveChunker` fallback**.

Ở CP5, chiến lược này ingest 8 documents thành 36 chunks. CP6 sử dụng real semantic embedding:

```text
Strategy           : heading_aware
Embedding backend  : gemini-embedding-001
Documents          : 8
Chunks loaded      : 36
Top-k              : 3
```

| # | Câu hỏi (Query)                                                                   | Top-1 Chunk truy xuất được (tóm tắt)                                                             | Điểm Score | Có liên quan không? | Câu trả lời của Agent (tóm tắt)                                                                                |
|---|-----------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------|-----------:|---------------------|----------------------------------------------------------------------------------------------------------------|
| 1 | How long can I borrow books?                                                      | `borrowing-books-undergraduate#0` — bảng Undergraduate Students, loan period 6 weeks             |     0.7045 | Có                  | Undergraduate students mượn 6 tuần; agent cũng phân biệt thêm reserve-book periods từ context khác             |
| 2 | How many reserve items may a student borrow at one time?                          | `course-reserves-student#0` — Book Reserves, chứa giới hạn tối đa 3 items                        |     0.8385 | Có                  | Students may borrow up to three reserve items at one time                                                      |
| 3 | How do I request library equipment, and how far in advance must I reserve it?     | `equipment-loans#0` — Requesting Equipment; top-2 `#1` chứa yêu cầu reserve trước ít nhất 1 ngày |     0.7839 | Có                  | Chọn “Reserve this item”, đăng nhập HoyaSearch và reserve ít nhất 1 ngày trước                                 |
| 4 | How long do Interlibrary Loan requests usually take to arrive?                    | `interlibrary-consortium-loans#3` — Items from Other Locations                                   |     0.7744 | Có                  | Average delivery time is 7–14 business days                                                                    |
| 5 | Where is food allowed in Lauinger Library, and what kinds of food are prohibited? | `library-use-policy#1` — General Policies; top-2 `#2` chứa danh sách food bị cấm                 |     0.8566 | Có                  | Food chỉ được phép ở tầng 2; pizza, hamburgers, fries, ice cream, hot subs và đồ ăn smelly/greasy/messy bị cấm |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** **5 / 5**

### Chấm điểm Retrieval Quality

| Câu      |      Điểm | Lý do                                                                      |
|----------|----------:|----------------------------------------------------------------------------|
| Q1       |       2/2 | Chunk đúng ở top-1 sau metadata filter; agent trả lời đúng `6 weeks`       |
| Q2       |       2/2 | Answer-bearing chunk ở top-1; agent trả lời đúng giới hạn 3 items          |
| Q3       |       2/2 | Top-1 và top-2 kết hợp đủ hai ý của gold answer; agent tổng hợp đúng       |
| Q4       |       2/2 | Chunk chứa `7-14 business days` ở top-1; agent trả lời đúng                |
| Q5       |       2/2 | Top-1 và top-2 kết hợp đủ location + prohibited foods; agent tổng hợp đúng |
| **Tổng** | **10/10** | **5/5 query đạt yêu cầu**                                                  |

### A/B Metadata Filtering — Q1

**Không filter:**

```text
1. score=0.7067  borrowing-books-faculty         audience=faculty
2. score=0.7045  borrowing-books-undergraduate   audience=student
3. score=0.6792  course-reserves-student         audience=student
```

**Có `metadata_filter={"audience": "student"}`:**

```text
1. score=0.7045  borrowing-books-undergraduate   audience=student
2. score=0.6792  course-reserves-student         audience=student
3. score=0.6603  course-reserves-student         audience=student
```

Metadata filtering có ích rõ ràng: nếu không filter, policy faculty đứng top-1. Khi lọc `audience=student`, tài liệu
faculty
bị loại khỏi candidate set và undergraduate policy trở thành top-1, đúng với gold answer.

### Failure Case & Phân tích

**Failure case:** Q1 khi chạy không có metadata filter.

**Hiện tượng:** `borrowing-books-faculty` đứng top-1 dù benchmark cần policy dành cho undergraduate student.

**Nguyên nhân:** Query “How long can I borrow books?” cố ý không nêu audience. Hai tài liệu faculty và undergraduate có
chủ đề, cấu trúc và từ vựng rất giống nhau nên cosine similarity không đủ để tự xác định đúng đối tượng.

**Cách sửa:** lọc candidate trước similarity search bằng `metadata_filter={"audience": "student"}`. Trong hệ thống thực
tế, nếu chưa biết audience thì application nên hỏi lại người dùng hoặc lấy audience từ session/profile trước retrieval.

### Nhận xét về Heading-aware Strategy

Heading-aware chunking giữ được context section tốt trên corpus policy Markdown. Q3 và Q5 cho thấy một gold answer có
thể cần tổng hợp từ hai chunk liên tiếp; cả hai đều xuất hiện trong top-2 nên agent vẫn trả lời đầy đủ. Vì vậy, đánh giá
retrieval chỉ theo `doc_id` là chưa đủ; cần kiểm tra nội dung chunk trong top-k.

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**

> Điền sau phần demo/so sánh nhóm khi có kết quả thực tế của các thành viên còn lại.

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí                                        | Điểm tự đánh giá |
|-------------------------------------------------|-----------------:|
| Khởi động (Warm-up)                             |            5 / 5 |
| Hướng tiếp cận của tôi (My Approach)            |          10 / 10 |
| Hoàn thiện code (Core Implementation — tests)   |          30 / 30 |
| Dự đoán độ tương tự (Similarity Predictions)    |            5 / 5 |
| Kết quả truy xuất của tôi (Competition Results) |          10 / 10 |
| **Tổng phần cá nhân**                           |      **60 / 60** |