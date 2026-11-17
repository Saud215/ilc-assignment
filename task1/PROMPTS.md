## AI Use
The answers were drafted using Claude Chat and Claude Code.

## Starting Prompt
Help me design the system described below.

## Claude Code Prompt
Write one Python script, draw_architecture.py, in this folder. Rules: do not run any git command, do not read any .env file, do not install anything (matplotlib is already installed in .venv), and make no network calls. You may run the script with .venv/bin/python draw_architecture.py and look at the image it makes.

Check the installed matplotlib version and use its real API. Use plain, readable code with short comments, simple enough for a beginner. Use a clean, normal style. Do not imitate handwriting.

The script draws a system architecture diagram and saves it as architecture.png in the same folder: landscape, about 11.7 by 8.3 inches, 200 dpi, white background, no axes.

LAYOUT, top to bottom:
1. Top centre: a box "Student's browser (lab PC, weak WiFi)".
2. Left side, outside the region box: a box "CDN" with the smaller line "static exam page files only, no student data".
3. A large dashed rectangle labelled in its top-left corner "AWS Mumbai region (data stays in India)". Inside it:
   a. "Load balancer" near the top.
   b. Below it, "App servers", drawn as three boxes stacked slightly behind each other like a pile of cards, to show a group that grows and shrinks. The front box has the lines "one application: exams | results | fees" and "2 normally, more on a schedule".
   c. A bottom row of three boxes: "Redis" (lines: "ready-made results", "exam deadlines"), "PostgreSQL" (lines: "primary + standby copy", "ACID transactions"), "Queue" (line: "payment events").
4. Right side, outside the region box: a box "Payment gateway" with the smaller line "Indian, RBI-regulated".

ARROWS, each with a short label next to it:
- browser to CDN: "exam page"
- browser to load balancer: "answers, results, fees"
- browser to payment gateway: "pays"
- load balancer to app servers (no label)
- app servers to Redis, to PostgreSQL and to Queue (no labels)
- payment gateway to app servers: "confirms payment (signed)"

NUMBERED MARKERS: small circles with a number, placed next to: 1 the browser, 2 Redis, 3 the payment gateway arrow. A key at the bottom of the image:
"1  Answers are saved in the browser first, then sent to the server. The server holds the exam clock."
"2  Results are prepared once before release and read from the cache."
"3  One unique order ID per fee. Paid only when the gateway confirms it to the server."

Title at the top: "University exams, results and fees platform".

Nothing may overlap: no box over another box, no label over an arrow or a box, and all text inside its box. Run the script, look at architecture.png yourself, and fix any overlap or cut-off text before you finish. Then show me the script and tell me what you checked.