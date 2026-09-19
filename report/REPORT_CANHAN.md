# Báo Cáo Cá Nhân — Lab 7: Embedding & Vector Store

**Họ tên:** Nguyễn Đức Danh **Nhóm:** DDCC **Ngày:** 19/09/2026

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

> **Sẽ chốt sau CP4.** Thiết kế hiện tại dự kiến chuẩn hóa mỗi `Document` thành một record gồm `id`, `content`,
> `metadata` và embedding. `add_documents` chỉ lưu các `Document` được truyền vào, không tự thực hiện chunking.
>
> Khi search, query được embed bằng cùng `embedding_fn`, sau đó tính similarity với các record và sắp xếp score giảm dần
> để trả về tối đa `top_k` kết quả.

**`search_with_filter` + `delete_document` — hướng tiếp cận:**

> **Sẽ chốt sau CP4.** Metadata filtering được thực hiện **trước similarity search** để các slot `top_k` chỉ cạnh tranh
> giữa những document hợp lệ. Nếu search trước rồi mới filter, các document sai metadata có thể chiếm hết top-k và làm mất
> kết quả phù hợp.
>
> `delete_document` sẽ xóa tất cả record có `metadata["doc_id"]` khớp với document cần xóa, cho phép một document gốc có
> nhiều chunk nhưng vẫn xóa được toàn bộ cùng lúc.

### Tác tử KnowledgeBaseAgent

**`answer` — hướng tiếp cận:**

> **Sẽ chốt sau CP4.** Agent dự kiến thực hiện ba bước: retrieve các chunk top-k, xây dựng context có đánh số nguồn, sau
> đó gọi `llm_fn`.
>
> Prompt sẽ yêu cầu model chỉ trả lời dựa trên context được cung cấp và không tự suy đoán khi context không chứa đáp án.
> Các chunk sẽ được đánh số để hỗ trợ source traceability.

---

## 3. Hoàn thiện code (Core Implementation) — Cá nhân (30 điểm)

Vượt qua bộ kiểm thử là điều kiện tính điểm phần này.

### Kết Quả Kiểm Thử

```

Kết quả:

```text
collected 42 items / 19 deselected / 23 selected

TestClassBasedInterfaces::test_chunker_classes_exist PASSED

TestFixedSizeChunker:
- test_chunks_respect_size PASSED
- test_correct_number_of_chunks_no_overlap PASSED
- test_empty_text_returns_empty_list PASSED
- test_no_overlap_no_shared_content PASSED
- test_overlap_creates_shared_content PASSED
- test_returns_list PASSED
- test_single_chunk_if_text_shorter PASSED

TestSentenceChunker:
- test_chunks_are_strings PASSED
- test_respects_max_sentences PASSED
- test_returns_list PASSED
- test_single_sentence_max_gives_many_chunks PASSED

TestRecursiveChunker:
- test_chunks_within_size_when_possible PASSED
- test_empty_separators_falls_back_gracefully PASSED
- test_handles_double_newline_separator PASSED
- test_returns_list PASSED

TestComputeSimilarity:
- test_identical_vectors_return_1 PASSED
- test_opposite_vectors_return_minus_1 PASSED
- test_orthogonal_vectors_return_0 PASSED
- test_zero_vector_returns_0 PASSED

TestCompareChunkingStrategies:
- test_counts_are_positive PASSED
- test_each_strategy_has_count_and_avg_length PASSED
- test_returns_three_strategies PASSED

23 passed, 19 deselected in 0.03s
```

**Số lượng bài test vượt qua (pass):** 23 / 42

---

## 4. Dự đoán độ tương tự (Similarity Predictions) — Cá nhân (5 điểm)

Các dự đoán dưới đây được ghi trước khi chạy embedding/similarity experiment.

| Cặp | Câu A                                                | Câu B                                                            | Dự đoán          | Điểm thực tế | Đúng? |
|-----|------------------------------------------------------|------------------------------------------------------------------|------------------|--------------|-------|
| 1   | `Students can borrow books for six weeks.`           | `Undergraduate learners may keep library books for six weeks.`   | Cao              | TODO         | TODO  |
| 2   | `Faculty members can place books on course reserve.` | `Professors may request books for course reserves.`              | Cao              | TODO         | TODO  |
| 3   | `Equipment must be reserved one day in advance.`     | `Library equipment reservations should be made ahead of pickup.` | Cao              | TODO         | TODO  |
| 4   | `Interlibrary loans may take several business days.` | `Pizza is not permitted on most library floors.`                 | Thấp             | TODO         | TODO  |
| 5   | `Students can borrow reserve items.`                 | `Faculty can choose reserve loan periods.`                       | Trung bình / Cao | TODO         | TODO  |

**Kết quả nào bất ngờ nhất? Điều này nói gì về cách embeddings biểu diễn ý nghĩa?**

> **TODO sau khi chạy experiment.** So sánh prediction với similarity score thực tế, đặc biệt ở cặp 5 vì hai câu cùng
> thuộc domain `course reserves` nhưng nói về hai audience và hai hành động khác nhau. Đây là trường hợp hữu ích để quan
> sát embedding ưu tiên mức độ giống chủ đề hay giống ý nghĩa chi tiết.

---

## 5. Kết quả truy xuất của tôi (Competition Results) — Cá nhân (10 điểm)

Chạy **5 câu hỏi đánh giá của nhóm** trên mã nguồn cá nhân của bạn trong gói `src`. **5 câu hỏi này phải trùng với các thành viên cùng nhóm** (xem `REPORT_NHOM.md`).

| # | Câu hỏi (Query) | Top-1 Chunk truy xuất được (tóm tắt) | Điểm Score | Có liên quan không? (Relevant) | Câu trả lời của Agent (tóm tắt) |
|---|-----------------|--------------------------------------|------------|--------------------------------|---------------------------------|
| 1 | TODO CP5        | TODO                                 | TODO       | TODO                           | TODO                            |
| 2 | TODO CP5        | TODO                                 | TODO       | TODO                           | TODO                            |
| 3 | TODO CP5        | TODO                                 | TODO       | TODO                           | TODO                            |
| 4 | TODO CP5        | TODO                                 | TODO       | TODO                           | TODO                            |
| 5 | TODO CP5        | TODO                                 | TODO       | TODO                           | TODO                            |

**Bao nhiêu câu hỏi trả về chunk có liên quan trong top-3?** **TODO / 5**

**Điều hay nhất tôi học được từ thành viên khác / nhóm khác (qua demo):**

> **TODO sau phần demo/so sánh nhóm.**

---

## Tự Đánh Giá (Phần Cá Nhân)

| Tiêu chí                                        | Điểm tự đánh giá |
|-------------------------------------------------|-----------------:|
| Khởi động (Warm-up)                             |              / 5 |
| Hướng tiếp cận của tôi (My Approach)            |             / 10 |
| Hoàn thiện code (Core Implementation — tests)   |             / 30 |
| Dự đoán độ tương tự (Similarity Predictions)    |              / 5 |
| Kết quả truy xuất của tôi (Competition Results) |             / 10 |
| **Tổng phần cá nhân**                           |         **/ 60** |
