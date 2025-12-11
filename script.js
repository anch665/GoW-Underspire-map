// Утилиты
function posToStr(pos) {
  return JSON.stringify(pos);
}
function strToPos(s) {
  return JSON.parse(s);
}

function parsePosition(roomId) {
  let s = String(roomId).padStart(4, '0');
  if (s.length !== 4) return null;
  const y = parseInt(s.slice(0, 2), 10);
  const x = parseInt(s.slice(2, 4), 10);
  if (isNaN(y) || isNaN(x)) return null;
  return (y >= 0 && y < 20 && x >= 0 && x < 20) ? [y, x] : null;
}

function parseRoomsDict(roomDict) {
  const result = new Map();
  for (const [coordKey, roomId] of Object.entries(roomDict)) {
    const pos = parsePosition(coordKey);
    if (pos) result.set(posToStr(pos), roomId);
  }
  return result;
}

function parseMapData(dataJson) {
  try {
    const data = dataJson.result.Info.UnderspireData;
    const mapData = data.Map;
    const completedIds = data.Completed || [];
    const treasureInfo = data.TreasureRoomInfo || {};
    const bossInfo = data.BossRoomInfo || {};
    const gatesInfo = data.Gates || {};
    const collectedRaw = data.Collected || [];
    const current_node = data.CurrentNode;

    const currentPos = parsePosition(current_node);
    const completedCoords = new Set();
    for (const id of completedIds) {
      const pos = parsePosition(id);
      if (pos) completedCoords.add(posToStr(pos));
    }

    const treasureRooms = parseRoomsDict(treasureInfo);
    const bossRooms = parseRoomsDict(bossInfo);

    const collectedCoords = new Set();
    for (const cid of collectedRaw) {
      const pos = parsePosition(cid);
      if (pos) collectedCoords.add(posToStr(pos));
    }

    const collectedTreasureCoords = new Set();
    for (const posStr of collectedCoords) {
      if (treasureRooms.has(posStr)) {
        collectedTreasureCoords.add(posStr);
      }
    }

    // Gates
    const gateCells = new Map(); // key: posStr → gateId
    const gatePairs = new Map(); // key: gateId → [pos1, pos2]

    for (const [gateId, gateData] of Object.entries(gatesInfo)) {
      const node = gateData.Node;
      const direction = gateData.Dir;
      const basePos = parsePosition(node);
      if (!basePos) continue;

      const [y, x] = basePos;
      let cells;
      if (direction === 1) {
        cells = [[y, x], [y, x + 1]];
      } else if (direction === 0) {
        cells = [[y, x], [y - 1, x]];
      } else {
        continue;
      }

      const valid = cells.every(([cy, cx]) => cy >= 0 && cy < 20 && cx >= 0 && cx < 20);
      if (valid) {
        const cellStrs = cells.map(pos => posToStr(pos));
        gatePairs.set(gateId, cells);
        for (const posStr of cellStrs) {
          gateCells.set(posStr, gateId);
        }
      }
    }

    return {
      mapData,
      completedCoords,
      treasureRooms,
      bossRooms,
      gateCells,
      gatePairs,
      collectedTreasureCoords,
      currentPos,
      error: null
    };
  } catch (e) {
    return { error: `Ошибка парсинга: ${e.message || e}` };
  }
}

// DOM элементы
const errorBox = document.getElementById('errorBox');
const statsDiv = document.getElementById('stats');
const mapGrid = document.getElementById('mapGrid');
const legendDiv = document.getElementById('legend');

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.style.display = 'block';
}

function hideError() {
  errorBox.style.display = 'none';
}

function renderLegend() {
  const items = [
    { style: "border: 3px solid #00BFFF", label: "🔵 Текущая позиция" },
    { style: "background-color: #FF4500; color: white;", label: "Ворота (ID — номер пары)" },
    { style: "background-color: #FFD700; color: black;", label: "Сокровища" },
    { style: "border: 3px solid #00BFFF", label: "💎 Собранные сокровища" },
    { style: "background-color: #32CD32; color: black;", label: "Боссы" },
    { style: "background-color: #87CEFA; color: black;", label: "Пройденные комнаты" },
    { style: "background-color: #ffffff; color: black;", label: "Не пройденные комнаты" },
    { style: "background-color: #2a2a2a; color: white;", label: "Пустые клетки (15)" },
    { style: "border: 3px solid #FFA500", label: "🟠 Пройденные особые комнаты (рамка)" },
  ];

  legendDiv.innerHTML = items.map(item => `
    <div class="legend-item">
      <div class="legend-color" style="${item.style}"></div>
      <span>${item.label}</span>
    </div>
  `).join('');
}

function renderMap(data) {
  const {
    mapData,
    completedCoords,
    treasureRooms,
    bossRooms,
    gateCells,
    gatePairs,
    collectedTreasureCoords,
    currentPos
  } = data;

  const rows = 20, cols = 20;

  let totalRooms = 0, completedCount = 0;
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      if (mapData[y][x] !== 15) {
        totalRooms++;
        if (completedCoords.has(posToStr([y, x]))) {
          completedCount++;
        }
      }
    }
  }
  const remaining = totalRooms - completedCount;
  const treasureCount = treasureRooms.size;
  const collectedTreasureCount = collectedTreasureCoords.size;
  const bossCount = bossRooms.size;
  const gateCount = gatePairs.size;

  statsDiv.innerHTML = `
    <p>
      Пройдено: ${completedCount} | 
      Сокровищ: ${treasureCount} (собрано: ${collectedTreasureCount}) | 
      Боссов: ${bossCount} | 
      Ворот: ${gateCount}
    </p>
    <p><strong>Комнат для открытия: ${remaining} из ${totalRooms}</strong></p>
  `;

  // Оси X
  let axisLabels = '';
  for (let x = 0; x < cols; x++) {
    axisLabels += `<div class="axis-label">${x}</div>`;
  }

  // Сетка
  let gridHtml = '';
  gridHtml += `<div class="axis-label"></div>${axisLabels}<div class="axis-label"></div>`;

  for (let y = 0; y < rows; y++) {
    gridHtml += `<div class="axis-label y-label">${y}</div>`;
    for (let x = 0; x < cols; x++) {
      const cellValue = mapData[y][x];
      const pos = [y, x];
      const posStr = posToStr(pos);
      const isCurrent = currentPos && currentPos[0] === y && currentPos[1] === x;

      let cssClasses = ['cell'];
      let displayText = '';
      let isSpecial = false;

      if (gateCells.has(posStr)) {
        const gid = gateCells.get(posStr);
        cssClasses.push('gate');
        displayText = gid;
        isSpecial = true;
      } else if (treasureRooms.has(posStr)) {
        cssClasses.push('treasure');
        displayText = treasureRooms.get(posStr);
        isSpecial = true;
      } else if (bossRooms.has(posStr)) {
        cssClasses.push('boss');
        displayText = bossRooms.get(posStr);
        isSpecial = true;
      } else if (cellValue === 15) {
        cssClasses.push('empty');
      } else if (completedCoords.has(posStr)) {
        cssClasses.push('completed');
      } else {
        cssClasses.push('room');
      }

      if (isSpecial && completedCoords.has(posStr)) {
        cssClasses.push('special-completed');
      }

      if (isCurrent) {
        cssClasses.push('current-location');
      }

      if (collectedTreasureCoords.has(posStr)) {
        cssClasses.push('collected-treasure');
      }

      gridHtml += `<div class="${cssClasses.join(' ')}" data-original-id="${cellValue}">${displayText}</div>`;
    }
    gridHtml += `<div class="axis-label y-label">${y}</div>`;
  }

  gridHtml += `<div class="axis-label"></div>${axisLabels}<div class="axis-label"></div>`;
  mapGrid.innerHTML = gridHtml;
  renderLegend();
}

// Основная логика загрузки
function processData(dataJson) {
  const parsed = parseMapData(dataJson);
  if (parsed.error) {
    showError(parsed.error);
    return;
  }
  hideError();
  renderMap(parsed);
}

// Загрузка файла
document.getElementById('fileInput').addEventListener('change', function (e) {
  const file = e.target.files[0];
  if (!file) return;
  if (file.size > 5 * 1024 * 1024) {
    showError("Файл слишком большой (макс. 5 МБ)");
    return;
  }
  const reader = new FileReader();
  reader.onload = function (e) {
    try {
      const json = JSON.parse(e.target.result);
      processData(json);
    } catch (err) {
      showError("Некорректный JSON-файл: " + err.message);
    }
  };
  reader.readAsText(file);
});

// Drag & Drop
const dropZone = document.getElementById('dropZone');
const fileInput = document.getElementById('fileInput');

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
  dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
});

['dragleave', 'drop'].forEach(eventName => {
  dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
});

dropZone.addEventListener('drop', handleDrop, false);

function handleDrop(e) {
  const dt = e.dataTransfer;
  const files = dt.files;
  if (files.length) {
    fileInput.files = files;
    const event = new Event('change', { bubbles: true });
    fileInput.dispatchEvent(event);
  }
}

// Загрузка из текста
document.getElementById('submitTextBtn').addEventListener('click', function () {
  const text = document.getElementById('jsonTextarea').value.trim();
  if (!text) {
    alert('Введите JSON');
    return;
  }
  try {
    const json = JSON.parse(text);
    processData(json);
  } catch (err) {
    showError("Ошибка парсинга JSON: " + err.message);
  }
});
