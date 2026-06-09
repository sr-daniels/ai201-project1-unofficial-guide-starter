"""
app.py — Gradio interface for the roommate-matching RAG system.

Thin UI layer: it calls ask() from query.py and renders the grounded answer
plus the programmatically-attributed source list.
"""

import gradio as gr

from query import ask


def handle_query(question):
    result = ask(question)
    # `result["sources"]` comes straight from the retrieved chunks, so this list
    # is always consistent with what the answer was grounded on.
    sources = "\n".join(f"• {s}" for s in result["sources"])
    return result["answer"], sources


with gr.Blocks() as demo:
    gr.Markdown(
        "# NCSU Roommate and Community Matching RAG\n"
        "Answers are grounded **only** in retrieved documents. "
        "If the documents don't cover your question, the system says so."
    )

    inp = gr.Textbox(label="Your question")
    btn = gr.Button("Ask")
    answer = gr.Textbox(label="Answer", lines=8)
    sources = gr.Textbox(label="Retrieved from", lines=4)

    btn.click(handle_query, inputs=inp, outputs=[answer, sources])
    inp.submit(handle_query, inputs=inp, outputs=[answer, sources])

demo.launch()