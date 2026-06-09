# The Unofficial Guide — Project 1

---

## Domain

I decided to choose roommate/community matching as my domain because I'm personally interested in the intersection of AI and interpersonal relationships. I believe AI can be used to help connect people of similar backgrounds and interests together. Also, unless you're extroverted or outgoing it's usually hard to find people from similar backgrounds. Introverts who reside at home for most of the day or haven't found communities to regularly be apart of stuggle find connections. There are general roomate matching services available at each university but these services usually don't go in depth as they have thousands of university students to serve. Also, the limited amount of official channels that are actually available online still require work to search and read through this profile. In an age federally declared at the "loneliness epidemic" (especially for young adults ofs age 18-24) this project seeks to mitigate those issues and use technology to connect people together rather than bring them further apart.

---

## Document Sources

<!-- List every source you collected documents from.
     Be specific: include URLs, subreddit names, forum thread titles, or file names.
     Aim for variety — sources that together cover different subtopics or perspectives. -->

| # | Source | Type | URL or file path |
|---|--------|------|-----------------|
| 1 | NC State CSC student organizations|University department web page (HTML) | https://csc.ncsu.edu/academics/student-organizations/|
| 2 |NC State MAE student organizations | University department web page (HTML)| https://mae.ncsu.edu/student-organizations/|
| 3 |NC State CCEE student organizations |University department web page (HTML) | https://ccee.ncsu.edu/student-organizations/|
| 4 | NC State ISE student organizations|University department web page (HTML) |https://ise.ncsu.edu/current-students/student-organizations/ |
| 5 | NC State BAE student organizations|University department web page (HTML) | https://bae.ncsu.edu/academics/student-organizations/|
| 6 |Nature Human Behaviour, neural similarity and friendship |Peer-reviewed journal article |https://www.nature.com/articles/s41562-025-02266-7 |
| 7 |Frontiers in Psychology, personality homophily and group success | Peer-reviewed journal article| https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2020.00710/full|
| 8 | Simply Psychology, the science of adult friendships| Popular-science article| https://www.simplypsychology.com/articles/adult-friendships-research|
| 9 | APA Monitor, the science of friendship|Professional-association article | https://www.apa.org/monitor/2023/06/cover-story-science-friendship|
| 10 | Roomsurf, NC State roommate profiles (WITH PID REMOVED)|Roommate-matching site (user profiles) | https://www.roomsurf.com/north-carolina-state-university-roommates/|

---

## Chunking Strategy

<!-- Describe your chunking approach with enough specificity that someone else could reproduce it.
     Include:
     - Chunk size (characters or tokens) and why that size fits your documents
     - Overlap size and why (or why not) you used overlap
     - Any preprocessing you did before chunking (e.g., stripping HTML, removing headers)
     - What your final chunk count was across all documents -->

**Chunk size:** about 450 words per chunk.

**Overlap:** about 75 words (roughly one paragraph) between consecutive chunks, except for the Roomsurf profiles, which are handled separately (see below).

**Why these choices fit your documents:** My documents vary in size, documents coming from the roomate site for example are short in size with only a few words describing each person. Other sources like roomate posts from facebook are usually paragraph length while documents coming from research backed sources are several paragraphs long. This makes the chunk size need to be something that is adaptable. For example a fixed chunk size strategy would've worked for the first source mentioned (the roomate website), but this same strategy wouldn't work well for the research-backed documents. For this reason, I've decided to go with medium-sized chunks that account for ~ 450 words for my chunk size. If a key fact expands two adjacent chunks, I'll fall back on an overlap of about ~75 words to attempt to connect the two ideas together. This will leave longer documents with about one paragraph of overlap to be able to synchronize.


**Final chunk count:** 77 chunks across all sources.

---

## Embedding Model

<!-- Name the embedding model you used and explain your choice.
     Then answer: if you were deploying this system for real users and cost wasn't a constraint,
     what tradeoffs would you weigh in choosing a different model?
     Consider: context length limits, multilingual support, accuracy on domain-specific text,
     latency, and local vs. API-hosted. -->

**Model used:** all-MiniLM-L6-v2 via sentence-transformers


**Production tradeoff reflection:** If this were deploying to real users I would compare embedding models to see which one offers the best result. I think accuracy is most important for a project like this because the goal is to connect users with people they would actually get along with, so retrieving the most relevant information matters more than having a fast or cheap model. I would also consider how well the model understands student the content we're giving it (especially the content that is coming from social media sites such as Reddit or Facebook).


---

## Grounded Generation

<!-- Explain how your system enforces grounding — how does it prevent the LLM from answering
     beyond the retrieved documents?
     Describe both your system prompt (what instruction you gave the model) and any structural
     choices (e.g., how you formatted the context, whether you filtered low-relevance chunks).
     Do not just say "I told it to use the documents" — show the actual instruction or explain
     the mechanism. -->

**System prompt grounding instruction:** Generation runs through Groq using llama-3.3-70b-versatile. The retrieval step passes only the top-5 retrieved chunks to the model as the context for the answer, and the generation step is instructed to answer strictly from that supplied context rather than from the model's general knowledge. The grounding is observable in the system's behavior: every answer is framed as "According to the context...," and when the context does not contain what was asked (for example, a query for a major that no Roomsurf profile lists) the system responds that it does not have that information instead of guessing or answering "no." The exact wording of this instruction lives in query.py, which was provided in the starter repo rather than written by me.


**How source attribution is surfaced in the response:** Each answer ends with a bulleted list of the source document filenames for the chunks that were retrieved to produce it (for example, roomsurf.txt, www_frontiersin_org_..._00710_full.txt), so the reader can trace every answer back to the documents it came from.

---

## Evaluation Report

| # | Question | Expected answer | System response (summarized) | Retrieval quality | Response accuracy |
|---|----------|-----------------|------------------------------|-------------------|-------------------|
| 1 | I'm interested in agricultural robotics. What club could help me meet people with that interest? | RoboPack, because it builds autonomous robots for agricultural tasks. | Identified RoboPack as a team that builds an autonomous robot performing an agricultural task; cited the MAE, BAE, and CSC org pages. | Relevant | Accurate |
| 2 | Why would it be harder for a night owl and an early riser to become friends? | Mismatched schedules give the two fewer opportunities to interact. | Explained that propinquity and repeated unplanned encounters build friendship, and that differing schedules reduce the chances to be in proximity. | Relevant | Accurate |
| 3 | Are there any engineering students currently looking for roommates? | Yes, multiple roommate listings include students majoring in engineering. | Answered yes, but listed all five Roomsurf profiles (Alpha through Epsilon) as engineering students, including Alpha (Linguistics) and Delta (Sports/Fitness Management), who are not. | Relevant | Partially accurate |
| 4 | Do roommates with similar personalities bond better than those with different ones? | Yes. Research on personality homophily found similarity in traits like conscientiousness and neuroticism predicted group formation, and greater personality differences were associated with weaker group bonding. | Answered that similarity in conscientiousness predicted group success and bonding, and that larger personality differences were tied to worse outcomes; cited the Frontiers homophily study. | Relevant | Accurate |
| 5 | My potential roommate and I clicked right away, does that mean we'll actually get along long-term? | Not necessarily. Lasting friendships are rooted in deeper pre-existing similarities, and maintaining a relationship takes ongoing effort. | Answered that an initial click is a good start but not a guarantee, emphasizing that propinquity, repeated contact, and deliberate maintenance determine long-term success; cited the Nature and Simply Psychology sources. | Partially relevant | Accurate |



---

## Failure Case Analysis

**Question that failed:** Question 3, "Are there any engineering students currently looking for roommates?"

**What the system returned:** "There are several engineering students looking for roommates, including Alpha Female, Beta Male, Gamma Female, Delta Male, and Epsilon Male." Alpha majors in Foreign Languages/Linguistics and Delta in Sports/Fitness Management, so two of the five listed are not engineering students. The correct answer is Beta, Gamma, and Epsilon.

**Root cause (tied to a specific pipeline stage):** This is a chunking failure that propagated into generation. All five Roomsurf profiles ended up stored in a single chunk (roomsurf.txt, chunk #0) instead of one chunk per profile. The per-profile delimiter the chunker relies on was not present in the embedded version of the file, so the entire source collapsed into one chunk. Retrieval did its job and returned that chunk, but because the chunk concatenates five students with five different majors, the generation model had no clean boundary telling it which major belonged to which person. Given a single blob listing five names and five majors and asked specifically about engineering students, the model over-generalized and attributed engineering to all five rather than only the three it applies to.

**What you would change to fix it:** Guarantee one profile per chunk using a robust delimiter, for example splitting on the "Roommate-seeking student profile from Roomsurf." marker line rather than the fragile object-replacement glyph, which is easy to lose when the file is copied or edited. With each profile isolated in its own chunk, the model only ever sees one student's major at a time and cannot conflate them. A stronger fix would additionally parse each profile's major into chunk metadata and filter retrieval on major == "Engineering", so only true matches are returned in the first place.

---

## Spec Reflection

**One way the spec helped you during implementation:**
The planning.md spec gave me concrete, testable targets that turned vague intentions into something I could build and check against. The chunking parameters (about 450 words, 75-word overlap), the embedding choice (all-MiniLM-L6-v2), and the top-k of 5 were all decided up front, so implementation became a matter of matching the spec rather than improvising. The five evaluation questions were especially useful: they defined what "working" meant, and running them repeatedly is what surfaced the retrieval problems I then had to debug.

**One way your implementation diverged from the spec, and why:**
The implementation diverged in three related ways. First, planning.md described a single fixed chunking strategy, but I had to special-case the Roomsurf source into per-profile chunks (and add a "roommate-seeking" framing line), because the generic 450-word packer blended several students into one embedding and made it impossible to retrieve an individual profile. Second, I had to rewrite evaluation questions 4 and 5: the original versions (about a quiet, calm living space and a messy roommate) asked about things the corpus simply doesn't contain, so I changed them to questions the friendship-research sources can actually answer (personality similarity and whether an early connection lasts). Third, because generation is grounded strictly in the retrieved context, the system returns "I don't have that information" when no profile matches a requested major, rather than answering a flat "no," which is a more honest behavior than the spec anticipated but still a divergence from how I originally imagined the system would respond.

---

## AI Usage

**Instance 1**

- *What I gave the AI:* My Chunking Strategy section from planning.md, a sample raw Roomsurf profile, and the problem that all the profiles were being merged into one chunk so an "engineering students" query couldn't find anyone.
- *What it produced:* A chunk_roomsurf() function that splits the Roomsurf dump one profile per chunk on the profile-marker glyph and strips the repeated "Create an Account to see" boilerplate, plus a routing line in main() so only Roomsurf files use it while everything else keeps the generic chunker.
- *What I changed or overrode:* I made the call on the fidelity question myself, whether to add a "Roommate-seeking student profile from Roomsurf." framing line that isn't in the original scrape, and chose to add it directly to the source text rather than inject it in code, so the change is visible in the data.

**Instance 2**

- *What I gave the AI:* My Retrieval Approach section from planning.md (the all-MiniLM-L6-v2 choice and top-k of 5) and the pipeline diagram, and asked it to implement the embedding-and-retrieval stage.
- *What it produced:* embed_and_retrieve.py, which loads the chunks, embeds them with the local model, stores them in ChromaDB with source and chunk-index metadata under cosine similarity, and exposes a retrieve(query, k=5) function.
- *What I changed or overrode:* I directed it to remove a hardcoded personal file path and anchor the chunks path to the script's own location instead, and after discovering that an old source (cdep12246.pdf) kept appearing in results, I had it switch the store to delete-and-recreate the collection on each run so stale chunks from previous corpora stop lingering.
