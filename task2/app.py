"""Web UI for the career fit report, built with Gradio.

Run: .venv/bin/python app.py
It opens on this computer only (127.0.0.1) and never creates a public share link.
"""

import json
import os

import gradio as gr
import openai
from dotenv import load_dotenv

import llm_adapter
import pipeline
import render
import scoring

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(APP_DIR, "sample_student.json")

QUESTIONS = scoring.load_questions()
ITEMS = QUESTIONS["items"]
QUESTIONS_PER_TAB = 10

REPORT_BUTTON_TEXT = "Get my career fit report"
BUSY_BUTTON_TEXT = "Working on your report..."

# Keep error details short on screen.
MAX_DETAIL_CHARS = 200


def scale_choices():
    """Radio choices as (label, value) pairs, so a radio returns the number 0 to 4."""
    choices = []
    for step in QUESTIONS["scale"]:
        choices.append((step["label"], step["value"]))
    return choices


def unsure_value():
    """The scale value labelled "Unsure", used as the default answer."""
    for step in QUESTIONS["scale"]:
        if step["label"] == "Unsure":
            return step["value"]
    raise ValueError('questions.json has no scale label "Unsure".')


# ---------- button handlers ----------


def fill_sample():
    """Load sample_student.json into the form: 30 answers, then the about text."""
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        sample = json.load(f)
    values = list(sample["answers"])
    values.append(sample["about"])
    return tuple(values)


def screen(status="", scores="", summary="", cards="", review="", notes="",
           cache="", tokens="", busy=False):
    """Values for every output component, in the order of the outputs list in build_app()."""
    if busy:
        # Greyed out while working, so the report cannot be requested twice.
        button = gr.update(value=BUSY_BUTTON_TEXT, interactive=False)
    else:
        button = gr.update(value=REPORT_BUTTON_TEXT, interactive=True)
    return (status, scores, summary, cards, review, notes, cache, tokens, button)


def shorten(text):
    if len(text) <= MAX_DETAIL_CHARS:
        return text
    return text[:MAX_DETAIL_CHARS] + "..."


def missing_api_key_name():
    """Name of the API key variable if it is not set, else "". Never returns the key."""
    try:
        key_name = llm_adapter.load_config()["provider"]["api_key_env"]
    except Exception:
        return ""
    # Same lookup as llm_adapter: .env first, then the shell environment.
    load_dotenv(llm_adapter.ENV_PATH)
    if os.getenv(key_name):
        return ""
    return key_name


def error_card_for(error):
    """Pick a friendly title and a short reason for a failure."""
    # Subclasses are checked before their parent classes (APIStatusError last).
    if isinstance(error, pipeline.StepError):
        return render.error_html(
            "The AI reply did not pass the checks",
            "It was retried and still failed, so no report was made. Please try again. "
            "Details: " + shorten(str(error)),
        )
    if isinstance(error, openai.RateLimitError):
        return render.error_html(
            "The AI service is busy",
            "Too many requests or the usage limit was reached. Wait a minute and try again.",
        )
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return render.error_html(
            "The API key was not accepted",
            "Check the key in your .env file, then restart the app.",
        )
    if isinstance(error, openai.APIConnectionError):
        return render.error_html(
            "Could not reach the AI service",
            "Check your internet connection and try again.",
        )
    if isinstance(error, openai.NotFoundError):
        return render.error_html(
            "Model not found",
            "Check the model IDs and base_url in config.json.",
        )
    if isinstance(error, openai.APIStatusError):
        return render.error_html(
            "The AI service returned an error",
            f"Status {error.status_code}. Please try again later.",
        )

    key_name = missing_api_key_name()
    if key_name:
        return render.error_html(
            "API key missing",
            f"Set {key_name} in a .env file (see .env.example), then restart the app.",
        )
    if isinstance(error, ValueError):
        # Our own config checks raise ValueError with a clear message.
        return render.error_html("There is a problem in the settings", shorten(str(error)))

    return render.error_html(
        "Something went wrong",
        f"Unexpected error ({type(error).__name__}). Please try again.",
    )


def correction_was_rejected(notes):
    """True when pipeline.py noted that Validate's corrected fits were not used."""
    # Matches the start of the note text written in pipeline.run_pipeline.
    for note in notes:
        if note.startswith("Validate's correction was rejected"):
            return True
    return False


def make_report(*form_values):
    """Run the pipeline for the form values (30 answers, then the about text).

    This is a generator: the first yield shows the working state at once,
    the last yield shows the report or an error card. Gradio keeps the
    event pending until the generator ends, so a second click is ignored.
    """
    answers = list(form_values[:len(ITEMS)])
    about = form_values[len(ITEMS)]

    yield screen(status=render.working_html(), busy=True)

    # Check the answers first, so a bad answer gets its own clear message.
    try:
        scoring.score_answers(answers)
    except ValueError as error:
        yield screen(status=render.error_html("Some answers are not valid", str(error)))
        return

    try:
        result = pipeline.run_pipeline(answers, about)
    except Exception as error:
        # One line for the person running the app. The page gets a friendly card.
        print(f"Report failed: {type(error).__name__}: {shorten(str(error))}")
        yield screen(status=error_card_for(error))
        return

    report = result["report"]
    rejected = correction_was_rejected(result["notes"])
    yield screen(
        scores=render.scores_html(result["sc"], result["top"]),
        summary=render.summary_html(report["sum"]),
        cards=render.cards_html(report["fits"]),
        review=render.review_html(result["review"], rejected),
        notes=render.notes_html(result["notes"]),
        cache=render.cache_html(result["cached"]),
        tokens=render.token_table_html(result["usage"]),
    )


# ---------- page layout ----------


def build_app():
    """Build the page. Nothing is launched here."""
    # analytics_enabled=False: the app sends no usage data to Gradio.
    with gr.Blocks(title="Career Fit Report", analytics_enabled=False) as demo:
        gr.Markdown("# Career Fit Report")
        gr.Markdown(
            "Answer 30 short questions about activities, add a few lines about yourself, "
            "and get three career ideas that fit your interests."
        )
        gr.HTML(render.notice_html())

        gr.Markdown(
            "**How much would you like doing each activity?** "
            "The questions are on three tabs. Any question you skip counts as Unsure."
        )

        # Three tabs of ten questions, so the page is not one endless list.
        radios = []
        with gr.Tabs():
            for start in range(0, len(ITEMS), QUESTIONS_PER_TAB):
                group = ITEMS[start:start + QUESTIONS_PER_TAB]
                with gr.Tab(f"Questions {group[0]['n']} to {group[-1]['n']}"):
                    for item in group:
                        radio = gr.Radio(
                            choices=scale_choices(),
                            value=unsure_value(),
                            label=f"{item['n']}. {item['text']}",
                        )
                        radios.append(radio)

        about_box = gr.Textbox(
            label="About me",
            lines=5,
            placeholder="For example: I enjoy biology and drawing. "
                        "I am good at explaining things to friends.",
            info="Your interests, strengths, favourite subjects and any career goal. "
                 "Only the first 150 words are used.",
        )

        with gr.Row():
            fill_button = gr.Button("Fill sample answers", variant="secondary")
            report_button = gr.Button(REPORT_BUTTON_TEXT, variant="primary")

        # Outputs, in the order screen() returns them.
        status_out = gr.HTML()
        scores_out = gr.HTML()
        summary_out = gr.HTML()
        cards_out = gr.HTML()
        review_out = gr.HTML()
        notes_out = gr.HTML()
        cache_out = gr.HTML()
        tokens_out = gr.HTML()

        gr.HTML(render.footer_html(QUESTIONS["source"]))

        form_inputs = radios + [about_box]
        fill_button.click(fill_sample, inputs=[], outputs=form_inputs)
        report_button.click(
            make_report,
            inputs=form_inputs,
            outputs=[
                status_out,
                scores_out,
                summary_out,
                cards_out,
                review_out,
                notes_out,
                cache_out,
                tokens_out,
                report_button,
            ],
            # Our own "working" card is the main loading sign; keep the timer only.
            show_progress="minimal",
        )

    return demo


if __name__ == "__main__":
    app = build_app()
    # 127.0.0.1 = reachable from this computer only. share=False = no public link.
    app.launch(server_name="127.0.0.1", share=False)
