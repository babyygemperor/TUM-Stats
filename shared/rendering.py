from html import escape


GRADE_COLOURS = {
    "1.0": "rgb(0,255,0)", "1.1": "rgb(12,255,0)", "1.2": "rgb(25,255,0)", "1.3": "rgb(38,255,0)",
    "1.4": "rgb(51,255,0)", "1.5": "rgb(63,255,0)", "1.6": "rgb(76,255,0)", "1.7": "rgb(89,255,0)",
    "1.8": "rgb(101,255,0)", "1.9": "rgb(114,255,0)", "2.0": "rgb(127,255,0)", "2.1": "rgb(140,255,0)",
    "2.2": "rgb(153,255,0)", "2.3": "rgb(165,255,0)", "2.4": "rgb(178,255,0)", "2.5": "rgb(191,255,0)",
    "2.6": "rgb(204,255,0)", "2.7": "rgb(216,255,0)", "2.8": "rgb(229,255,0)", "2.9": "rgb(242,255,0)",
    "3.0": "rgb(255,255,0)", "3.1": "rgb(255,242,0)", "3.2": "rgb(255,229,0)", "3.3": "rgb(255,216,0)",
    "3.4": "rgb(255,204,0)", "3.5": "rgb(255,191,0)", "3.6": "rgb(255,178,0)", "3.7": "rgb(255,165,0)",
    "3.8": "rgb(255,153,0)", "3.9": "rgb(255,140,0)", "4.0": "rgb(255,127,0)", "4.1": "rgb(255,114,0)",
    "4.2": "rgb(255,101,0)", "4.3": "rgb(255,89,0)", "4.4": "rgb(255,76,0)", "4.5": "rgb(255,63,0)",
    "4.6": "rgb(255,51,0)", "4.7": "rgb(255,38,0)", "4.8": "rgb(255,25,0)", "4.9": "rgb(255,12,0)",
    "5.0": "rgb(255,0,0)", "5.0X": "rgb(255,0,50)", "5.0 X": "rgb(255,0,50)",
    "5.0 X Nicht erschienen": "rgb(255,0,50)", "5.0X Nicht erschienen": "rgb(255,0,50)",
    "5.0U": "rgb(255,0,50)", "5.0 U": "rgb(255,0,50)",
    "5.0 Ungültig": "rgb(255,0,50)", "5.0U Ungültig": "rgb(255,0,50)", "5.0 U Ungültig": "rgb(255,0,50)",
    "5.0 U Täuschung": "rgb(255,0,50)", "5.0U Täuschung": "rgb(255,0,50)",
    "5.0 U Ungültig/Täuschung": "rgb(255,0,50)", "5.0U Ungültig/Täuschung": "rgb(255,0,50)",
    "5.0Z": "rgb(255,0,50)", "5.0 Z": "rgb(255,0,50)",
    "5.0Z Zurückweisung": "rgb(255,0,50)", "5.0 Z Zurückweisung": "rgb(255,0,50)",
    "Unknown": "rgb(100,100,100)"
}

PASSING_GRADES = [
    "1.0", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "1.7", "1.8", "1.9",
    "2.0", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8", "2.9",
    "3.0", "3.1", "3.2", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9",
    "4.0"
]

ATTEMPT_GRADES = PASSING_GRADES + ["4.3", "4.7", "5.0", "B pass", "B", "N fail", "N"]

NOT_PRESENT_KEYS = ["5.0X", "5.0 X", "5.0 X Nicht erschienen", "5.0 X Nicht erschienen"]

REJECTION_KEYS = ["5.0Z", "5.0 Z", "5.0Z Zurückweisung", "5.0 Z Zurückweisung"]

CHEATING_KEYS = [
    "5.0U", "5.0 U", "5.0 Ungültig", "5.0U Ungültig", "5.0 U Ungültig",
    "5.0 U Täuschung", "5.0U Täuschung", "5.0 U Ungültig/Täuschung", "5.0U Ungültig/Täuschung"
]

REQUIRED_GRADES = ["1.0", "1.3", "1.7", "2.0", "2.3", "2.7", "3.0", "3.3", "3.7", "4.0", "4.3", "4.7", "5.0"]

SUMMARY_KEYS = [
    'Registered', 'Attempt made', 'Not present', 'Not valid/cheating', 'Rejection',
    'Percent. of exams failed', 'Average total', 'Average (assessed as passed)'
]


def highlight(text, query):
    text = escape(text)
    for word in query.split():
        if word:
            text = text.replace(word, f'<span class="highlight">{word}</span>')
    return text


def _get_value(key, value, data):
    dist = data['Grade distribution']

    if key == 'Registered':
        return sum(int(v) for v in dist.values())
    if key == 'Attempt made':
        return sum(int(v) for k, v in dist.items() if k in ATTEMPT_GRADES)
    if key == 'Not present':
        return sum(int(v) for k, v in dist.items() if k in NOT_PRESENT_KEYS)
    if key == 'Rejection':
        return sum(int(v) for k, v in dist.items() if k in REJECTION_KEYS)
    if key == 'Not valid/cheating':
        return sum(int(v) for k, v in dist.items() if k in CHEATING_KEYS)
    if key == 'Percent. of exams failed':
        total_students = _get_value('Registered', 0, data)
        passed = sum(int(v) for k, v in dist.items() if k in PASSING_GRADES + ["B pass", "B"])
        return f"{round((1.0 - (passed / total_students)) * 100, 2)}%"
    if key == 'Average total':
        total_students = _get_value('Registered', 0, data)
        grade = 0
        for k, v in dist.items():
            g = "5.0" if k.startswith("5.0") else k
            try:
                grade += int(v) * float(g)
            except ValueError as e:
                print(e)
        return round(grade / total_students, 3)
    if key == 'Average (assessed as passed)':
        grade = 0
        total_students = 0.0
        for k, v in dist.items():
            if k in PASSING_GRADES:
                grade += int(v) * float(k)
                total_students += float(v)
        if total_students == 0.0:
            return 0.0
        return round(grade / total_students, 3)
    return value


def _render_distribution(distribution, bar_width='5%'):
    for grade in REQUIRED_GRADES:
        if grade not in distribution:
            distribution[grade] = "0"

    total_candidates = sum(int(count) for count in distribution.values())
    html_content = '<div style="display: flex; flex-direction: row; align-items: flex-end; position: relative; margin-top:1em; margin-bottom:3em; padding-right:3em; margin-right:2em; margin-left:2em; width: auto; height: 24em; z-index: 100;">'
    html_content += '<div style="position: absolute; left: 0; height: 23em; width: 1px; background-color: black; bottom: 20px;"></div>'
    html_content += '<div style="position: absolute; width: 100%; height: 1px; background-color: black; bottom: 20px; left: 0;"></div>'

    first = True
    distribution = dict(sorted(distribution.items()))

    for grade, count in distribution.items():
        try:
            percentage = (int(count) / total_candidates) * 100
            bar_height = f"{int(count) / int(max(distribution.values(), key=int)) * 20}em"
        except ZeroDivisionError:
            percentage = 0
            bar_height = 0
        colour = GRADE_COLOURS.get(grade, "rgb(100,100,100)")
        if first:
            html_content += f'<div style="width: {bar_width}; margin: 0 0 0 1%; position: relative;">'
            first = False
        else:
            html_content += f'<div style="width: {bar_width}; position: relative;">'

        html_content += f'<div style="position: absolute; margin-left: 0; width: 100%; margin-top: 3.0em; height: {bar_height}; background-color: {colour}; bottom: 21px; z-index: 101">'
        if percentage > 0:
            html_content += f'<div style="color: black; text-align: center; position: absolute; bottom: 100%; width: 100%; margin-bottom: 1.0em">{percentage:.2f}%<br>{count} K.</div></div>'
        else:
            html_content += f'<div style="color: black; text-align: center; position: absolute; bottom: 100%; width: 100%; margin-bottom: 2.0em"><br>{count} K.</div></div>'
        html_content += f'<div style="position: absolute; width: 100%; text-align: center; margin-top: -1em;">{escape(str(grade))}</div>'
        html_content += '</div>'
    html_content += '</div>'
    return html_content


def json_to_html(json_data, query=None, bar_width='5%'):
    for key in SUMMARY_KEYS:
        if key not in json_data:
            json_data[key] = "-"

    html_content = ""
    distribution_html = ""

    title = json_data.get('Name', '')
    if query:
        title = highlight(title, query)
    else:
        title = escape(title)
    html_content += f"<h3>{title}</h3>\n"
    html_content += "<table>\n<tbody>\n"

    for key, value in json_data.items():
        if isinstance(value, dict):
            continue
        label_id = f"ST{abs(hash(key)) % 1000000000000}"
        display_value = highlight(str(value), query) if query else str(value)
        html_content += f"<tr><td><label for='{label_id}'>{escape(str(key))}:</label></td>"
        html_content += f"<td id='{label_id}'>{_get_value(key, display_value, json_data)}</td></tr>\n"

    html_content += f"<tr><td colspan='2'>{escape('Grade distribution')}: Percent % / grade\nK. = Number of candidates</td></tr>\n"
    distribution_html = _render_distribution(json_data["Grade distribution"], bar_width)
    html_content += "</tbody>\n</table>\n"
    html_content += distribution_html

    return html_content
