import json
import os
from flask import Flask, request

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5 MB limit


# ======================
# 🧩 Вспомогательные функции
# ======================

def _normalize_room_id(room_id):
    """
    Применяет специальные преобразования к ID комнат, начинающихся с '9'.
    Только для Completed и Collected.
    Примеры:
        9004 → 1004
        9906 → 1706
        9706 → 1906
    """
    s = str(room_id)
    if len(s) >= 2:
        prefix = s[:2]
        suffix = s[2:].zfill(2)  
        if prefix == '90':
            return '10' + suffix
        elif prefix == '99':
            return '17' + suffix
        elif prefix == '98':
            return '18' + suffix
        elif prefix == '97':
            return '19' + suffix
        elif prefix == '54':
            return '14' + suffix
        else:
            return s
    return s


def _parse_position(room_id):
    """Преобразует ID комнаты в (y, x). Поддерживает int и str."""
    s = str(room_id).zfill(4)
    if len(s) != 4:
        return None
    y, x = int(s[:2]), int(s[2:])
    return (y, x) if 0 <= y < 20 and 0 <= x < 20 else None


def _parse_rooms_dict(room_dict):
    """Парсит словарь {coord_str: room_id} → {(y, x): room_id}"""
    result = {}
    for coord_key, room_id in room_dict.items():
        pos = _parse_position(coord_key)
        if pos is not None:
            result[pos] = room_id
    return result


# ======================
# 🧩 Парсинг данных
# ======================
def parse_map_data(data_json):
    """Преобразует JSON-объект в данные для отображения карты"""
    try:
        map_data = data_json["result"]["Info"]["UnderspireData"]["Map"]
        completed_ids = data_json["result"]["Info"]["UnderspireData"]["Completed"]
        treasure_info = data_json["result"]["Info"]["UnderspireData"]["TreasureRoomInfo"]
        boss_info = data_json["result"]["Info"]["UnderspireData"]["BossRoomInfo"]
        gates_info = data_json["result"]["Info"]["UnderspireData"]["Gates"]
        collected_raw = data_json["result"]["Info"]["UnderspireData"]["Collected"]
        current_node = data_json["result"]["Info"]["UnderspireData"]["CurrentNode"]
    except KeyError as e:
        return None, f"Отсутствует ключ в JSON: {e}"

    current_pos = _parse_position(current_node)

    # Нормализуем ID в Completed (с учетом 90→10, 99→17, 97→19)
    normalized_completed = [_normalize_room_id(rid) for rid in completed_ids]
    completed_coords = {_parse_position(room_id) for room_id in normalized_completed}
    completed_coords = {pos for pos in completed_coords if pos is not None}

    treasure_rooms = _parse_rooms_dict(treasure_info)
    boss_rooms = _parse_rooms_dict(boss_info)

    # Также нормализуем Collected
    normalized_collected = [_normalize_room_id(cid) for cid in collected_raw]
    collected_coords = {_parse_position(cid) for cid in normalized_collected}
    collected_coords = {pos for pos in collected_coords if pos is not None}

    # Собранные сокровища = пересечение: есть сокровище И координата в Collected
    collected_treasure_coords = collected_coords & set(treasure_rooms.keys())

    # Ворота
    gate_cells = {}
    gate_pairs = {}
    for gate_id, gate_data in gates_info.items():
        node = gate_data["Node"]
        direction = gate_data["Dir"]
        base_pos = _parse_position(node)
        if base_pos is None:
            continue

        y, x = base_pos
        if direction == 1:  # горизонтально
            cells = [(y, x), (y, x + 1)]
        elif direction == 0:  # вертикально
            cells = [(y, x), (y - 1, x)]
        else:
            continue

        if all(0 <= cy < 20 and 0 <= cx < 20 for cy, cx in cells):
            gate_pairs[gate_id] = cells
            for cell in cells:
                gate_cells[cell] = gate_id

    return {
        "map_data": map_data,
        "completed_coords": completed_coords,
        "treasure_rooms": treasure_rooms,
        "boss_rooms": boss_rooms,
        "gate_cells": gate_cells,
        "gate_pairs": gate_pairs,
        "collected_treasure_coords": collected_treasure_coords,
        "current_pos": current_pos,
    }, None


# ======================
# 📦 Вспомогательные HTML-блоки
# ======================
def _render_upload_form():
    """Возвращает HTML-блок формы загрузки с горизонтальным расположением"""
    return '''
    <div class="upload-container">
        <!-- Левая часть: загрузка файла -->
        <div class="upload-box left">
            <h3>📥 Загрузить файл</h3>
            <div id="dropZone" class="drop-zone">
                Перетащите сюда JSON-файл или 
                <label for="fileInput" class="file-label">выберите файл</label>
                <input type="file" id="fileInput" name="jsonFile" accept=".json" style="display:none;">
            </div>
        </div>

        <!-- Правая часть: ввод JSON -->
        <div class="upload-box right">
            <h3>✍️ Вставить JSON</h3>
            <div class="text-input-container">
                <textarea id="jsonTextarea" name="jsonText" placeholder='{"result":{"Info":{...}}}'></textarea>
                <button type="button" id="submitTextBtn">Загрузить</button>
            </div>
        </div>
    </div>
    '''


def _render_error_box(error_msg):
    """Возвращает HTML-блок ошибки"""
    return f'''
    <div class="error-box">
        <h3>❌ Ошибка загрузки</h3>
        <pre>{error_msg}</pre>
    </div>
    '''


def _render_map_and_legend(data):
    """Генерирует HTML с картой слева и легендой справа"""
    if data is None:
        return ""

    map_data = data["map_data"]
    completed_coords = data["completed_coords"]
    treasure_rooms = data["treasure_rooms"]
    boss_rooms = data["boss_rooms"]
    gate_cells = data["gate_cells"]
    gate_pairs = data["gate_pairs"]
    collected_treasure_coords = data["collected_treasure_coords"]
    current_pos = data["current_pos"]

    rows, cols = 20, 20

    total_rooms = sum(1 for y in range(rows) for x in range(cols) if map_data[y][x] != 15)
    remaining_rooms = sum(
        1 for y in range(rows) for x in range(cols)
        if map_data[y][x] != 15 and (y, x) not in completed_coords
    )

    axis_labels = "".join(f'<div class="axis-label">{x}</div>' for x in range(cols))

    map_rows = []
    for y in range(rows):
        row_cells = ['<div class="axis-label y-label">' + str(y) + '</div>']
        for x in range(cols):
            cell_value = map_data[y][x]
            pos = (y, x)
            css_classes = ["cell"]
            display_text = ""

            is_special = False

            if pos in gate_cells:
                gid = gate_cells[pos]
                css_classes.append("gate")
                #display_text = str(gid)
                display_text = str(int(gid) + 1)
                is_special = True
            elif pos in treasure_rooms:
                css_classes.append("treasure")
                display_text = str(treasure_rooms[pos])
                is_special = True
            elif pos in boss_rooms:
                css_classes.append("boss")
                display_text = str(boss_rooms[pos])
                is_special = True
            elif cell_value == 15:
                css_classes.append("empty")
            elif pos in completed_coords:
                css_classes.append("completed")
            else:
                css_classes.append("room")

            # Подсветка пройденных ОСОБЫХ комнат — рамкой
            if is_special and pos in completed_coords:
                css_classes.append("special-completed")

            if current_pos == pos:
                css_classes.append("current-location")

            if pos in collected_treasure_coords:
                css_classes.append("collected-treasure")

            class_str = " ".join(css_classes)
            row_cells.append(f'<div class="{class_str}" data-original-id="{cell_value}">{display_text}</div>')

        row_cells.append('<div class="axis-label y-label">' + str(y) + '</div>')
        map_rows.append("".join(row_cells))

    legend_html = _render_legend()

    stats = f'''
    <p>
        Пройдено: {len(completed_coords)} | 
        Сокровищ: {len(treasure_rooms)} (собрано: {len(collected_treasure_coords)}) | 
        Боссов: {len(boss_rooms)} | 
        Ворот: {len(gate_pairs)}
    </p>
    <p><strong>Комнат для открытия: {remaining_rooms} из {total_rooms}</strong></p>
    '''

    return f'''
    {stats}
    <div class="map-legend-container">
        <div class="map-grid-container">
            <div class="map-grid">
                <div class="axis-label"></div>
                {axis_labels}
                <div class="axis-label"></div>
                {''.join(f'<div style="display:contents;">{row}</div>' for row in map_rows)}
                <div class="axis-label"></div>
                {axis_labels}
                <div class="axis-label"></div>
            </div>
        </div>
        <div class="legend">
            {legend_html}
        </div>
    </div>
    '''


def _render_legend():
    legend_items = [
        ('border: 5px solid #0000FF', 'inherit', 'Текущая позиция'),
        ('#FF4500', 'white', 'Ворота (ID — номер пары)'),
        ('#FFD700', 'black', 'Страж сокровища'),
        ('#32CD32', 'black', 'Босс(ключ)'),
        ('#87CEFA', 'black', 'Посещенные комнаты'),
        ('#ffffff', 'black', 'Комнаты'),
        ('border: 3px solid #FFA500', 'inherit', 'Пройденные особые комнаты'),
    ]

    items = []
    for bg, color, label in legend_items:
        if 'border' in bg:
            style = f"width:20px; height:20px; {bg};"
        else:
            style = f"width:20px; height:20px; background-color:{bg}; color:{color}; border:1px solid #000;"
        items.append(f'<div class="legend-item"><div class="legend-color" style="{style}"></div><span>{label}</span></div>')
    return ''.join(items)


# ======================
# 🎨 Основной шаблон
# ======================
def generate_html_page(data=None, error_msg=None):
    """Генерирует полную HTML-страницу"""
    upload_form = _render_upload_form()
    error_block = _render_error_box(error_msg) if error_msg else ""
    map_and_legend = _render_map_and_legend(data)

    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Underspire Map Live</title>
        <style>
            body {{
                background: #1e1e1e;
                color: white;
                font-family: Arial, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 20px;
                margin: 0;
            }}
            h2 {{
                margin-bottom: 15px;
            }}

            /* === Контейнер загрузки (две колонки) === */
            .upload-container {{
                display: flex;
                gap: 20px;
                width: 100%;
                max-width: 900px;
                margin-bottom: 20px;
            }}
            .upload-box {{
                background: #2d2d2d;
                padding: 15px;
                border-radius: 8px;
                flex: 1;
            }}
            .upload-box h3 {{
                margin-top: 0;
                font-size: 16px;
            }}

            /* === Drag & Drop === */
            .drop-zone {{
                border: 2px dashed #555;
                border-radius: 6px;
                padding: 20px;
                text-align: center;
                background: #252525;
                transition: background 0.3s;
                cursor: pointer;
                font-size: 14px;
            }}
            .drop-zone.drag-over {{
                background: #333;
                border-color: #4a90e2;
            }}
            .file-label {{
                color: #4a90e2;
                text-decoration: underline;
                cursor: pointer;
            }}
            .file-label:hover {{
                color: #357abd;
            }}

            /* === Текстовый ввод справа === */
            .text-input-container {{
                display: flex;
                gap: 8px;
                width: 100%;
            }}
            #jsonTextarea {{
                flex: 1;
                height: 120px;
                background: #1e1e1e;
                color: #0f0;
                border: 1px solid #444;
                border-radius: 4px;
                padding: 8px;
                font-family: monospace;
                resize: none;
            }}
            #submitTextBtn {{
                background: #4a90e2;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
                padding: 0 12px;
                font-size: 14px;
                height: 120px;
            }}
            #submitTextBtn:hover {{
                background: #357abd;
            }}

            /* === Ошибка === */
            .error-box {{
                background: #442222;
                padding: 15px;
                border-radius: 6px;
                margin: 10px 0;
                width: 100%;
                max-width: 900px;
                font-family: monospace;
            }}

            /* === Карта и легенда (в центре) === */
            .map-legend-container {{
                display: flex;
                gap: 20px;
                justify-content: center;
                margin-top: 10px;
            }}
            .map-grid-container {{
                width: fit-content;
            }}
            .map-grid {{
                display: grid;
                grid-template-columns: 32px repeat(20, 32px) 32px;
                grid-template-rows: auto repeat(20, 32px) auto;
                gap: 0;
                border: 2px solid #555;
            }}
            .axis-label {{
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 10px;
                background: #333;
                color: #aaa;
                user-select: none;
            }}
            .y-label {{
                background: #2d2d2d !important;
                border-right: 1px solid #555;
                border-left: 1px solid #555;
            }}
            .cell {{
                width: 32px;
                height: 32px;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 9px;
                border: 1px solid #000;
                box-sizing: border-box;
                position: relative;
            }}
            .empty {{ background-color: #2a2a2a; }}
            .room {{ background-color: #ffffff; color: #000; }}
            .completed {{ background-color: #87CEFA; color: #000; }}
            .treasure {{
                background-color: #FFD700;
                color: #000;
                font-weight: bold;
                font-size: 10px;
            }}
            .boss {{
                background-color: #32CD32;
                color: #000;
                font-weight: bold;
                font-size: 10px;
            }}
            .gate {{
                background-color: #FF4500;
                color: white;
                font-weight: bold;
                font-size: 10px;
            }}
            .current-location {{
                border: 5px solid #0000FF !important;
                box-sizing: border-box;
                width: 31px;
                height: 31px;
                z-index: 10;
            }}
            .collected-treasure {{
                border: 3px solid #00BFFF !important;
                box-sizing: border-box;
                width: 31px;
                height: 31px;
            }}
            .special-completed {{
                border: 3px solid #FFA500 !important;
                box-sizing: border-box;
                width: 31px;
                height: 31px;
            }}
            .cell:hover::after {{
                content: "ID: " attr(data-original-id);
                position: absolute;
                bottom: -24px;
                left: 50%;
                transform: translateX(-50%);
                background: rgba(0,0,0,0.85);
                color: white;
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                white-space: nowrap;
                z-index: 100;
            }}

            /* === Легенда справа === */
            .legend {{
                width: 280px;
                flex-shrink: 0;
                display: flex;
                flex-direction: column;
                gap: 8px;
            }}
            .legend-item {{
                display: flex;
                align-items: center;
                gap: 10px;
                background: #2a2a2a;
                padding: 8px;
                border-radius: 4px;
                font-size: 13px;
            }}
            .legend-color {{
                flex-shrink: 0;
            }}
        </style>
    </head>
    <body>
        <h2>Underspire Map Live (20×20)</h2>
        {error_block}
        {upload_form}
        {map_and_legend}

        <script>
            // === Авто-загрузка при выборе файла ===
            document.getElementById('fileInput').addEventListener('change', function(e) {{
                const file = e.target.files[0];
                if (!file) return;
                const formData = new FormData();
                formData.append('jsonFile', file);
                fetch('/upload', {{ method: 'POST', body: formData }})
                .then(r => r.text())
                .then(html => {{
                    document.open();
                    document.write(html);
                    document.close();
                }})
                .catch(err => alert('Ошибка загрузки файла: ' + err));
            }});

            // === Drag & Drop ===
            const dropZone = document.getElementById('dropZone');
            const fileInput = document.getElementById('fileInput');

            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {{
                dropZone.addEventListener(eventName, preventDefaults, false);
            }});

            function preventDefaults(e) {{
                e.preventDefault();
                e.stopPropagation();
            }}

            ['dragenter', 'dragover'].forEach(eventName => {{
                dropZone.addEventListener(eventName, highlight, false);
            }});

            ['dragleave', 'drop'].forEach(eventName => {{
                dropZone.addEventListener(eventName, unhighlight, false);
            }});

            function highlight() {{
                dropZone.classList.add('drag-over');
            }}

            function unhighlight() {{
                dropZone.classList.remove('drag-over');
            }}

            dropZone.addEventListener('drop', handleDrop, false);

            function handleDrop(e) {{
                const dt = e.dataTransfer;
                const files = dt.files;
                if (files.length) {{
                    fileInput.files = files;
                    const event = new Event('change', {{ bubbles: true }});
                    fileInput.dispatchEvent(event);
                }}
            }};

            // === Загрузка из текста ===
            document.getElementById('submitTextBtn').addEventListener('click', function() {{
                const text = document.getElementById('jsonTextarea').value.trim();
                if (!text) {{ alert('Введите JSON'); return; }}
                fetch('/upload', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: text
                }})
                .then(r => r.text())
                .then(html => {{
                    document.open();
                    document.write(html);
                    document.close();
                }})
                .catch(() => alert('Ошибка: некорректный JSON'));
            }});
        </script>
    </body>
    </html>
    '''


# ======================
# 🌐 Роуты Flask
# ======================
@app.route('/')
def index():
    if os.path.exists("map.json"):
        try:
            with open("map.json", "r", encoding="utf-8") as f:
                data_json = json.load(f)
            data, error = parse_map_data(data_json)
            return generate_html_page(data=data, error_msg=error)
        except Exception as e:
            return generate_html_page(error_msg=f"Ошибка загрузки map.json: {e}")
    else:
        return generate_html_page()


@app.route('/upload', methods=['POST'])
def upload_data():
    try:
        if request.is_json:
            data_json = request.get_json()
        else:
            file = request.files.get('jsonFile')
            if not file:
                return "Файл не выбран", 400
            data_json = json.load(file)

        data, error = parse_map_data(data_json)
        return generate_html_page(data=data, error_msg=error)
    except Exception as e:
        return generate_html_page(error_msg=f"Ошибка обработки данных: {e}")


# ======================
# ▶️ Запуск
# ======================
if __name__ == '__main__':
    print("🚀 Запуск сервера на http://localhost:5000")
    print("Нажмите Ctrl+C для остановки.\n")
    app.run(host='127.0.0.1', port=5000, debug=False)
