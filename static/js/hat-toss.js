/*
 * Hat Toss: the 404 page's ring-toss game.
 *
 * Every peg on the field is a pointed hat worn by a historical figure, or a
 * cone from a robotics game. Ring one to score; ring several in a row to build
 * a streak multiplier. Points add up to a lifetime total that unlocks new hats
 * (Bismarck's Pickelhaube is the starter), and every ringer drops gears to
 * spend in the Workshop on wider hoops, a longer aim guide, a gearbox and ring
 * skins. It is meant to be easy, not automatic: throws drift toward the
 * nearest hat, more strongly the closer they were.
 *
 * The world is a small 3D scene (metres, x across, y up, z away from the
 * thrower) projected onto a 2D canvas. Each hat is a solid of revolution
 * described by a profile of [height fraction, radius] points, so the same
 * profile draws the hat, decides whether a ring clears its tip, and finds
 * where a ringer comes to rest.
 *
 * Progress is per visitor and lives in localStorage; the game plays the same
 * without it, it just forgets between visits.
 */
(function () {
    'use strict';

    var root = document.querySelector('[data-hat-toss]');
    if (!root) return;
    var canvas = root.querySelector('.ht-canvas');
    var ctx = canvas && canvas.getContext && canvas.getContext('2d');
    if (!ctx) return;

    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // --- World constants ------------------------------------------------------
    var G = 9.8;
    var CAM_Y = 1.75;
    var CAM_Z = -1.3;
    var HAND = { x: 0, y: 0.7, z: 0.4 };
    var LAUNCH_ANGLE = 0.84;
    var ASSIST_RANGE = 2.4;     // metres: how far off a throw can be and still get help
    var ASSIST_PULL = 0.9;      // most of the miss a throw can have corrected
    var WOBBLE = 0.15;          // metres of random scatter on every throw
    var THICK = 0.022;          // half the ring's tube thickness
    var WALL_Z = 12.5;
    var FIELD_X = 4.2;
    var TILE = 0.61;            // a VEX field tile is two feet square
    var BANDS = [[3.2, 4.6], [5.2, 6.9], [7.4, 9.3]];

    // --- The hats ---------------------------------------------------------------
    // profile: [fraction of height, radius in metres], base to tip.
    // colors: [edge shade, highlight, body, deep shade] across the hat's width.
    var HATS = [
        {
            id: 'pickelhaube', name: 'Bismarck\'s Pickelhaube', who: 'Otto von Bismarck', origin: 'Prussia', era: '1842–1916',
            pts: 10, unlock: 0, h: 0.78,
            profile: [[0, 0.30], [0.04, 0.30], [0.06, 0.255], [0.38, 0.25], [0.5, 0.215], [0.58, 0.14],
                [0.6, 0.075], [0.64, 0.06], [0.67, 0.035], [1, 0.006]],
            colors: ['#050506', '#55555c', '#1d1d22', '#000000'], cap: '#2c2c32',
            fact: 'Prussia issued the spiked leather helmet in 1842, and Otto von Bismarck, the "Iron Chancellor" who united Germany in 1871, posed for portrait after portrait in his cuirassier\'s Pickelhaube. By 1916 the steel Stahlhelm had replaced it at the front.',
            decor: function (k) {
                var c = k.ctx;
                var g = c.createLinearGradient(k.sx - k.R(0.6) * k.s, 0, k.sx + k.R(0.6) * k.s, 0);
                g.addColorStop(0, '#6e5110');
                g.addColorStop(0.35, '#ffe58a');
                g.addColorStop(1, '#7d5c12');
                c.fillStyle = g;
                c.beginPath();
                c.moveTo(k.sx - k.R(0.6) * k.s, k.cy(0.6));
                c.lineTo(k.sx - k.R(0.67) * k.s, k.cy(0.67));
                c.lineTo(k.sx, k.cy(1));
                c.lineTo(k.sx + k.R(0.67) * k.s, k.cy(0.67));
                c.lineTo(k.sx + k.R(0.6) * k.s, k.cy(0.6));
                c.ellipse(k.sx, k.cy(0.6), k.R(0.6) * k.s, k.E(0.6) * k.R(0.6) * k.s, 0, 0, Math.PI);
                c.closePath();
                c.fill();
                k.band(0.585, 0.035, '#c9a227');
                k.band(0.05, 0.018, '#c9a227');
                // The eagle plate on the front.
                var p = k.pt(0, 0.3);
                c.fillStyle = '#e0b83a';
                c.beginPath();
                c.ellipse(p[0], p[1], 0.05 * k.s, 0.075 * k.s, 0, 0, Math.PI * 2);
                c.fill();
                c.beginPath();
                c.moveTo(p[0] - 0.13 * k.s, p[1] - 0.05 * k.s);
                c.lineTo(p[0], p[1] + 0.01 * k.s);
                c.lineTo(p[0] + 0.13 * k.s, p[1] - 0.05 * k.s);
                c.lineTo(p[0], p[1] + 0.05 * k.s);
                c.closePath();
                c.fill();
            }
        },
        {
            id: 'vexcone', name: 'In the Zone cone', who: 'VEX Robotics', origin: 'VEX Robotics Competition', era: '2017–18 season',
            pts: 12, unlock: 100, h: 0.62,
            profile: [[0, 0.3], [0.05, 0.3], [0.07, 0.19], [1, 0.03]],
            colors: ['#8a6a00', '#fff3a0', '#f5c400', '#6b5200'], cap: '#ffd84a',
            fact: 'VEX Robotics Competition\'s 2017–18 game, In the Zone, was all about yellow cones: robots grabbed them off the field and stacked them as high as they could on mobile goals, then carried the goals into scoring zones.',
            decor: function (k) {
                k.band(0.2, 0.012, 'rgba(110, 80, 0, 0.55)');
                k.band(0.5, 0.012, 'rgba(110, 80, 0, 0.55)');
                k.band(0.8, 0.012, 'rgba(110, 80, 0, 0.55)');
            }
        },
        {
            id: 'dunce', name: 'Duns Scotus\'s dunce cap', who: 'John Duns Scotus', origin: 'Scotland & Europe', era: '1300s–1900s',
            pts: 14, unlock: 300, h: 1.0,
            profile: [[0, 0.26], [1, 0.008]],
            colors: ['#b9b3a4', '#ffffff', '#efeadf', '#9e9788'], cap: '#ffffff',
            fact: 'John Duns Scotus (c. 1266–1308) was one of the sharpest thinkers of the Middle Ages, and the story goes that he praised the pointed cap for funnelling wisdom into the head. Later critics mocked his followers as "Dunses", and by the 1800s the cone had become a classroom punishment.',
            decor: function (k) {
                k.band(0.04, 0.02, '#6d6658');
                var p = k.pt(0, 0.24);
                k.ctx.fillStyle = '#2a2a2a';
                k.ctx.font = '700 ' + Math.max(8, 0.24 * k.s) + 'px "Space Mono", monospace';
                k.ctx.textAlign = 'center';
                k.ctx.textBaseline = 'middle';
                k.ctx.fillText('D', p[0], p[1] - 0.02 * k.s);
            }
        },
        {
            id: 'frccone', name: 'Charged Up cone', who: 'FIRST Robotics Competition', origin: 'FIRST Robotics Competition', era: '2023 season',
            pts: 16, unlock: 600, h: 0.85,
            profile: [[0, 0.38], [0.04, 0.38], [0.055, 0.21], [1, 0.035]],
            colors: ['#8f6c00', '#fff1a6', '#f7c600', '#6e5300'], cap: '#ffd83d',
            fact: 'In FIRST Robotics Competition\'s 2023 game, Charged Up, robots scored yellow traffic cones and purple cubes on a grid, dropping each cone over a pole by its open tip. Here, for once, the pole gets its revenge.',
            decor: function (k) {
                k.band(0.08, 0.02, 'rgba(110, 80, 0, 0.5)');
                k.ctx.fillStyle = 'rgba(60, 40, 0, 0.55)';
                k.ctx.font = '700 ' + Math.max(7, 0.075 * k.s) + 'px "Space Mono", monospace';
                k.ctx.textAlign = 'center';
                k.ctx.textBaseline = 'middle';
                var p = k.pt(0, 0.3);
                k.ctx.fillText('FRC', p[0], p[1]);
            }
        },
        {
            id: 'nasal', name: 'William the Conqueror\'s helmet', who: 'William the Conqueror', origin: 'Normandy & England', era: '1066',
            pts: 18, unlock: 1000, h: 0.68,
            profile: [[0, 0.24], [0.1, 0.24], [0.5, 0.2], [0.8, 0.11], [1, 0.01]],
            colors: ['#4b5058', '#e3e7ee', '#9aa1ab', '#30343a'], cap: '#c2c8d1',
            fact: 'The Bayeux Tapestry shows the Normans at Hastings in conical helmets with a nose guard. When a rumour spread that Duke William had fallen, he pushed his helmet back so his men could see his face, and the battle turned.',
            decor: function (k) {
                var c = k.ctx;
                k.band(0.06, 0.05, '#7d848e');
                [-0.7, -0.35, 0, 0.35, 0.7].forEach(function (u) { k.dot(u, 0.06, 0.012, '#e3e7ee'); });
                c.strokeStyle = 'rgba(48, 52, 58, 0.6)';
                c.lineWidth = Math.max(1, 0.012 * k.s);
                c.beginPath();
                for (var f = 0.1; f <= 0.98; f += 0.04) {
                    var p = k.pt(0, f);
                    if (f === 0.1) c.moveTo(p[0], p[1]); else c.lineTo(p[0], p[1]);
                }
                c.stroke();
                var n = k.pt(0, 0.08);
                c.fillStyle = '#7d848e';
                c.fillRect(n[0] - 0.024 * k.s, n[1], 0.048 * k.s, 0.15 * k.s);
            }
        },
        {
            id: 'hennin', name: 'Hennin of the Burgundian court', who: 'Court of Philip the Good', origin: 'Burgundy', era: '1400s',
            pts: 20, unlock: 1600, h: 1.25,
            profile: [[0, 0.19], [0.06, 0.18], [1, 0.012]],
            colors: ['#4d0a14', '#e0607a', '#a3182f', '#33050c'], cap: '#c43b52',
            fact: 'At the court of Philip the Good, Duke of Burgundy (1419–1467), the richest court in Europe, noblewomen wore the hennin: a steep cone of stiffened fabric with a sheer veil floating from its point. The tallest were said to clear doorways only with a stoop.',
            decor: function (k) {
                var c = k.ctx;
                var t = k.tip();
                c.fillStyle = 'rgba(255, 250, 240, 0.35)';
                c.beginPath();
                c.moveTo(t[0], t[1]);
                c.bezierCurveTo(t[0] + 0.5 * k.s, t[1] + 0.2 * k.s, t[0] + 0.55 * k.s, k.sy - 0.3 * k.s, t[0] + 0.42 * k.s, k.sy + 0.05 * k.s);
                c.lineTo(t[0] + 0.2 * k.s, k.sy - 0.1 * k.s);
                c.bezierCurveTo(t[0] + 0.25 * k.s, k.sy - 0.5 * k.s, t[0] + 0.15 * k.s, t[1] + 0.3 * k.s, t[0], t[1]);
                c.fill();
                k.band(0.03, 0.05, '#140406');
                [0.15, 0.3, 0.45, 0.6, 0.75].forEach(function (f, i) {
                    (i % 2 ? [-0.45, 0.45] : [-0.7, 0, 0.7]).forEach(function (u) { k.dot(u, f, 0.016, '#f2c94c'); });
                });
            }
        },
        {
            id: 'mitre', name: 'Becket\'s mitre', who: 'Thomas Becket', origin: 'Canterbury, England', era: '1162–1170',
            pts: 24, unlock: 2400, h: 0.95,
            profile: [[0, 0.2], [0.08, 0.2], [0.55, 0.19], [0.85, 0.12], [1, 0.01]],
            colors: ['#a8a294', '#ffffff', '#f1ece0', '#8a8475'], cap: '#ffffff',
            fact: 'Thomas Becket, Archbishop of Canterbury, quarrelled with his old friend King Henry II and was cut down in his own cathedral in 1170. Within three years he was a saint, and his shrine made Canterbury the great pilgrimage of medieval England.',
            decor: function (k) {
                var c = k.ctx;
                k.band(0.06, 0.07, '#d9a520');
                var a = k.pt(0, 0.08), b = k.pt(0, 0.97);
                c.strokeStyle = '#d9a520';
                c.lineWidth = Math.max(2, 0.07 * k.s);
                c.beginPath();
                c.moveTo(a[0], a[1]);
                c.lineTo(b[0], b[1]);
                c.stroke();
                var x = k.pt(0, 0.5);
                c.strokeStyle = '#8e1b1b';
                c.lineWidth = Math.max(1, 0.025 * k.s);
                c.beginPath();
                c.moveTo(x[0], x[1] - 0.09 * k.s);
                c.lineTo(x[0], x[1] + 0.09 * k.s);
                c.moveTo(x[0] - 0.06 * k.s, x[1] - 0.03 * k.s);
                c.lineTo(x[0] + 0.06 * k.s, x[1] - 0.03 * k.s);
                c.stroke();
            }
        },
        {
            id: 'qing', name: 'Li Hongzhang\'s summer hat', who: 'Li Hongzhang', origin: 'Qing China', era: '1800s',
            pts: 28, unlock: 3400, h: 0.62,
            profile: [[0, 0.38], [0.08, 0.33], [0.75, 0.08], [0.82, 0.055], [0.88, 0.07], [0.95, 0.05], [1, 0.01]],
            colors: ['#5c0a0a', '#ff6f6f', '#c41d1d', '#3d0505'], cap: '#e04040',
            fact: 'Qing officials wore a cone of woven bamboo covered in red silk fringe, with a jewel on top showing their rank. The statesman Li Hongzhang, who toured Europe and America in 1896, was among the very few granted the three-eyed peacock feather to hang behind his.',
            decor: function (k) {
                var c = k.ctx;
                var t = k.pt(0, 0.86);
                // Peacock feather trailing behind and to the side.
                c.strokeStyle = '#1f6b5c';
                c.lineWidth = Math.max(1, 0.03 * k.s);
                c.beginPath();
                c.moveTo(t[0], t[1]);
                c.quadraticCurveTo(t[0] + 0.32 * k.s, t[1] + 0.05 * k.s, t[0] + 0.42 * k.s, k.sy - 0.05 * k.s);
                c.stroke();
                [[0.22, 0.25], [0.34, 0.5], [0.41, 0.8]].forEach(function (e) {
                    var x = t[0] + e[0] * k.s, y = t[1] + (k.sy - t[1]) * e[1];
                    c.fillStyle = '#1aa37a';
                    c.beginPath();
                    c.ellipse(x, y, 0.045 * k.s, 0.03 * k.s, 0.6, 0, Math.PI * 2);
                    c.fill();
                    c.fillStyle = '#1b3fa0';
                    c.beginPath();
                    c.arc(x, y, 0.016 * k.s, 0, Math.PI * 2);
                    c.fill();
                });
                c.strokeStyle = 'rgba(80, 0, 0, 0.45)';
                c.lineWidth = Math.max(0.75, 0.006 * k.s);
                c.beginPath();
                [-0.9, -0.6, -0.3, 0, 0.3, 0.6, 0.9].forEach(function (u) {
                    var a = k.pt(u * 0.25, 0.75), b = k.pt(u, 0.06);
                    c.moveTo(a[0], a[1]);
                    c.lineTo(b[0], b[1]);
                });
                c.stroke();
                k.band(0.04, 0.03, '#2b2b2b');
                k.dot(0, 0.9, 0.05, '#2f6fd6');
            }
        },
        {
            id: 'kabuto', name: 'Katō Kiyomasa\'s kabuto', who: 'Katō Kiyomasa', origin: 'Japan', era: '1590s',
            pts: 32, unlock: 4800, h: 1.15,
            profile: [[0, 0.34], [0.04, 0.34], [0.07, 0.2], [0.3, 0.2], [0.7, 0.14], [0.92, 0.07], [1, 0.012]],
            colors: ['#0b0b0d', '#5c5c66', '#1e1e24', '#000000'], cap: '#3a2222',
            fact: 'The samurai general Katō Kiyomasa (1562–1611) went to war in a towering helmet shaped like a courtier\'s tall eboshi cap. It made him easy to spot across a battlefield, which was rather the point: commanders wanted to be seen.',
            decor: function (k) {
                var c = k.ctx;
                k.band(0.06, 0.04, '#b8892c');
                var p = k.pt(0, 0.45);
                c.fillStyle = '#c62828';
                c.beginPath();
                c.arc(p[0], p[1], 0.075 * k.s, 0, Math.PI * 2);
                c.fill();
                c.strokeStyle = '#b8892c';
                c.lineWidth = Math.max(1, 0.012 * k.s);
                c.stroke();
                // Lacquered neck guard plates.
                [0.012, 0.025].forEach(function (f) { k.band(f, 0.012, '#7a1b1b'); });
            }
        },
        {
            id: 'tiara', name: 'Ashurbanipal\'s royal tiara', who: 'Ashurbanipal', origin: 'Assyria', era: 'c. 650 BC',
            pts: 36, unlock: 6400, h: 0.82,
            profile: [[0, 0.2], [0.72, 0.235], [0.74, 0.11], [0.8, 0.09], [1, 0.012]],
            colors: ['#7a6a4a', '#fff8e0', '#e8dcc0', '#5a4c30'], cap: '#f7efda',
            fact: 'In the Lion Hunt reliefs from his palace at Nineveh, now in the British Museum, Ashurbanipal, king of Assyria, wears a tall crown that ends in a small point. The same king gathered the first great library of the ancient world.',
            decor: function (k) {
                [0.08, 0.36, 0.66].forEach(function (f) { k.band(f, 0.04, '#c9962a'); });
                [-0.7, -0.35, 0, 0.35, 0.7].forEach(function (u) {
                    k.ring(u, 0.22, 0.03, '#c9962a');
                    k.ring(u, 0.52, 0.03, '#c9962a');
                });
                k.dot(0, 0.85, 0.04, '#c9962a');
            }
        },
        {
            id: 'hedjet', name: 'Narmer\'s white crown', who: 'King Narmer', origin: 'Upper Egypt', era: 'c. 3100 BC',
            pts: 42, unlock: 8400, h: 0.92,
            profile: [[0, 0.2], [0.3, 0.19], [0.65, 0.125], [0.82, 0.085], [0.9, 0.095], [0.96, 0.07], [1, 0.01]],
            colors: ['#a49d86', '#fffdf3', '#ebe5d0', '#857d66'], cap: '#fffdf3',
            fact: 'The Narmer Palette, carved around 3100 BC, shows King Narmer in the tall White Crown of Upper Egypt on one side and the red crown of Lower Egypt on the other: one of the earliest pictures of a named ruler, and of Egypt as one kingdom.',
            decor: function (k) {
                var c = k.ctx;
                var p = k.pt(0, 0.08);
                c.strokeStyle = '#d9a520';
                c.lineWidth = Math.max(1, 0.022 * k.s);
                c.beginPath();
                c.moveTo(p[0], p[1] + 0.02 * k.s);
                c.bezierCurveTo(p[0] - 0.05 * k.s, p[1] - 0.04 * k.s, p[0] + 0.05 * k.s, p[1] - 0.07 * k.s, p[0], p[1] - 0.12 * k.s);
                c.stroke();
                c.fillStyle = '#d9a520';
                c.beginPath();
                c.ellipse(p[0], p[1] - 0.13 * k.s, 0.025 * k.s, 0.03 * k.s, 0, 0, Math.PI * 2);
                c.fill();
            }
        },
        {
            id: 'saka', name: 'Skunkha\'s pointed cap', who: 'Skunkha', origin: 'Central Asian steppe', era: 'c. 520 BC',
            pts: 50, unlock: 11000, h: 1.0,
            profile: [[0, 0.23], [0.15, 0.2], [1, 0.008]],
            colors: ['#4a1d0c', '#d77a45', '#9c4320', '#2e1006'], cap: '#c0612f',
            fact: 'Darius the Great\'s Behistun Inscription names the Saka tigraxauda, "the Saka who wear pointed hats". Their captured chief Skunkha was added to the end of the carved line of rebel kings, the only one still wearing his tall cap.',
            decor: function (k) {
                var c = k.ctx;
                c.fillStyle = '#7a3014';
                [-1, 1].forEach(function (side) {
                    var a = k.pt(side * 0.98, 0.12);
                    c.beginPath();
                    c.moveTo(a[0], a[1]);
                    c.lineTo(a[0] + side * 0.03 * k.s, k.sy + 0.06 * k.s);
                    c.lineTo(a[0] - side * 0.08 * k.s, k.sy + 0.08 * k.s);
                    c.lineTo(a[0] - side * 0.09 * k.s, a[1] + 0.02 * k.s);
                    c.closePath();
                    c.fill();
                });
                c.strokeStyle = '#f0b48c';
                c.lineWidth = Math.max(1, 0.01 * k.s);
                c.setLineDash([0.03 * k.s, 0.025 * k.s]);
                c.beginPath();
                var s0 = k.pt(0.15, 0.02);
                c.moveTo(s0[0], s0[1]);
                for (var f = 0.1; f <= 1.001; f += 0.1) {
                    var p = k.pt(0.15 * (1 - f), f);
                    c.lineTo(p[0], p[1]);
                }
                c.stroke();
                c.setLineDash([]);
                k.band(0.06, 0.03, '#e2a23b');
            }
        }
    ];
    var HAT_BY_ID = {};
    HATS.forEach(function (h) { HAT_BY_ID[h.id] = h; });

    var UPGRADES = [
        { id: 'ring', name: 'Wider rings', blurb: 'More room to clear the tip.', costs: [40, 90, 180], values: [0.45, 0.5, 0.56, 0.62] },
        { id: 'guide', name: 'Aim guide', blurb: 'See more of the arc while you pull back.', costs: [30, 70, 150], values: [0.28, 0.42, 0.58, 0.75] },
        { id: 'gearbox', name: 'Gearbox', blurb: 'One more gear for every ringer.', costs: [50, 110, 220], values: [0, 1, 2, 3] },
        { id: 'bag', name: 'Bigger bag', blurb: 'More rings every round.', costs: [60, 140], values: [10, 12, 14] }
    ];
    var SAVER = { cost: 25, max: 3 };
    var SKINS = [
        { id: 'maroon', name: 'Mepham maroon', cost: 0, colors: ['#5e0000', '#c8676a'] },
        { id: 'gold', name: 'Trophy gold', cost: 30, colors: ['#8a6514', '#ffe066'] },
        { id: 'steel', name: 'Field steel', cost: 45, colors: ['#3b4048', '#dfe4ea'] },
        { id: 'neon', name: 'Neon', cost: 60, colors: ['#0a6b3a', '#7dffb3'] },
        { id: 'rainbow', name: 'Rainbow', cost: 120, colors: null }
    ];

    // --- Saved progress -----------------------------------------------------------
    var KEY = 'mepham-hat-toss';
    var state = loadState();

    function loadState() {
        var base = {
            best: 0, lifetime: 0, gears: 0, rounds: 0, ringers: 0, bestStreak: 0,
            up: { ring: 0, guide: 0, gearbox: 0, bag: 0 }, saves: 0,
            skin: 'maroon', skins: ['maroon'], sound: true,
            unlocked: ['pickelhaube'], seen: ['pickelhaube'], rung: {}
        };
        try {
            var saved = JSON.parse(localStorage.getItem(KEY) || 'null');
            if (saved && typeof saved === 'object') {
                Object.keys(base).forEach(function (key) {
                    if (saved[key] !== undefined && typeof saved[key] === typeof base[key]) base[key] = saved[key];
                });
            }
        } catch (err) {
            // Private mode or blocked storage: play without saving.
        }
        UPGRADES.forEach(function (u) {
            var level = base.up[u.id];
            base.up[u.id] = typeof level === 'number' ? clamp(Math.floor(level), 0, u.costs.length) : 0;
        });
        if (base.skins.indexOf(base.skin) === -1) base.skin = 'maroon';
        return base;
    }

    function saveState() {
        try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (err) { /* see loadState */ }
    }

    function upgrade(id) {
        var u = UPGRADES.filter(function (x) { return x.id === id; })[0];
        return u.values[state.up[id]];
    }

    // --- Small helpers ------------------------------------------------------------
    function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }
    function rand(lo, hi) { return lo + Math.random() * (hi - lo); }
    function fmt(n) { return Math.round(n).toLocaleString('en-US'); }
    function easeOut(t) { return 1 - Math.pow(1 - t, 3); }

    function radiusAt(def, y) {
        var f = y / def.h, p = def.profile;
        if (f >= 1) return 0;
        if (f <= 0) return p[0][1];
        for (var i = 0; i < p.length - 1; i++) {
            if (f <= p[i + 1][0]) {
                var t = (f - p[i][0]) / ((p[i + 1][0] - p[i][0]) || 1);
                return p[i][1] + (p[i + 1][1] - p[i][1]) * t;
            }
        }
        return 0;
    }

    // A ringer slides down until the hat is as wide as the ring.
    function restHeight(def, R) {
        for (var y = def.h; y > 0; y -= def.h / 240) {
            if (radiusAt(def, y) >= R - THICK) return y;
        }
        return 0.012;
    }

    function star(c, x, y, size, color) {
        c.fillStyle = color;
        c.beginPath();
        for (var i = 0; i < 10; i++) {
            var r = i % 2 ? size * 0.45 : size;
            var a = -Math.PI / 2 + i * Math.PI / 5;
            c[i ? 'lineTo' : 'moveTo'](x + Math.cos(a) * r, y + Math.sin(a) * r);
        }
        c.closePath();
        c.fill();
    }

    // --- Projection --------------------------------------------------------------
    var view = { W: 0, H: 0, F: 1, horizon: 0 };

    function project(x, y, z) {
        var D = Math.max(0.3, z - CAM_Z);
        var s = view.F / D;
        return { x: view.W / 2 + x * s, y: view.horizon + (CAM_Y - y) * s, s: s, D: D };
    }

    // How round a horizontal circle at height y looks from the camera.
    function eAt(y, D) {
        return clamp(Math.sin(Math.atan2(CAM_Y - y, D)), 0.06, 1);
    }

    // --- Drawing hats ---------------------------------------------------------------
    function hatKit(c, def, v) {
        var h = def.h;
        function R(f) { return radiusAt(def, f * h); }
        function cy(f) { return v.sy - f * h * v.s; }
        function E(f) { return eAt(f * h, v.D); }
        function pt(u, f) {
            var r = R(f);
            return [v.sx + u * r * v.s, cy(f) + Math.sqrt(Math.max(0, 1 - u * u)) * E(f) * r * v.s];
        }
        return {
            ctx: c, sx: v.sx, sy: v.sy, s: v.s, R: R, cy: cy, E: E, pt: pt,
            tip: function () { return [v.sx, cy(1)]; },
            band: function (f, w, color) {
                var r = R(f) * 1.01;
                c.beginPath();
                c.ellipse(v.sx, cy(f), r * v.s, E(f) * r * v.s, 0, 0, Math.PI);
                c.lineWidth = Math.max(1, w * v.s);
                c.strokeStyle = color;
                c.stroke();
            },
            dot: function (u, f, rad, color) {
                var p = pt(u, f);
                c.fillStyle = color;
                c.beginPath();
                c.arc(p[0], p[1], Math.max(1, rad * v.s), 0, Math.PI * 2);
                c.fill();
            },
            ring: function (u, f, rad, color) {
                var p = pt(u, f);
                c.strokeStyle = color;
                c.lineWidth = Math.max(0.75, 0.004 * v.s);
                c.beginPath();
                c.arc(p[0], p[1], Math.max(1, rad * v.s), 0, Math.PI * 2);
                c.stroke();
            }
        };
    }

    // v: { sx, sy, s, D } with (sx, sy) the centre of the hat's base on screen.
    function drawHat(c, def, v, silhouette) {
        var p = def.profile, h = def.h;
        var wide = 0;
        p.forEach(function (q) { wide = Math.max(wide, q[1]); });
        var fill = c.createLinearGradient(v.sx - wide * v.s, 0, v.sx + wide * v.s, 0);
        fill.addColorStop(0, def.colors[0]);
        fill.addColorStop(0.32, def.colors[1]);
        fill.addColorStop(0.6, def.colors[2]);
        fill.addColorStop(1, def.colors[3]);
        c.save();
        c.lineJoin = 'round';
        for (var i = 0; i < p.length - 1; i++) {
            var y0 = p[i][0] * h, r0 = p[i][1], y1 = p[i + 1][0] * h, r1 = p[i + 1][1];
            var c0 = v.sy - y0 * v.s, c1 = v.sy - y1 * v.s;
            c.beginPath();
            c.ellipse(v.sx, c0, r0 * v.s, eAt(y0, v.D) * r0 * v.s, 0, Math.PI, 0, true);
            c.lineTo(v.sx + r1 * v.s, c1);
            c.ellipse(v.sx, c1, Math.max(0.01, r1 * v.s), eAt(y1, v.D) * r1 * v.s, 0, 0, Math.PI, true);
            c.closePath();
            c.fillStyle = fill;
            c.fill();
            c.strokeStyle = 'rgba(0, 0, 0, 0.28)';
            c.lineWidth = 1;
            c.stroke();
            // A brim or ledge: show its top face.
            var next = p[i + 2];
            if (next && r1 - next[1] > 0.04 && (next[0] - p[i + 1][0]) * h < 0.06) {
                c.beginPath();
                c.ellipse(v.sx, c1, r1 * v.s, eAt(y1, v.D) * r1 * v.s, 0, 0, Math.PI * 2);
                c.fillStyle = def.cap;
                c.fill();
                c.stroke();
            }
        }
        if (def.decor) def.decor(hatKit(c, def, v));
        if (silhouette) {
            c.globalCompositeOperation = 'source-atop';
            c.fillStyle = 'rgba(14, 6, 6, 0.94)';
            c.fillRect(v.sx - 1.2 * v.s, v.sy - 1.5 * h * v.s, 2.4 * v.s, 2 * h * v.s);
        }
        c.restore();
    }

    // --- Drawing rings ---------------------------------------------------------------
    function ringStyle(c, x, rx, skinId) {
        var skin = SKINS.filter(function (s) { return s.id === skinId; })[0] || SKINS[0];
        if (!skin.colors) {
            var g = c.createLinearGradient(x - rx, 0, x + rx, 0);
            ['#ff4d4d', '#ffb84d', '#ffe14d', '#5ce07a', '#4dc3ff', '#9b6bff'].forEach(function (col, i, all) {
                g.addColorStop(i / (all.length - 1), col);
            });
            return { dark: 'rgba(0, 0, 0, 0.45)', light: g };
        }
        return { dark: skin.colors[0], light: skin.colors[1] };
    }

    // part: 'all', 'back' (far half) or 'front' (near half)
    function drawRing(c, x, y, z, R, part, spin, skinId) {
        var p = project(x, y, z);
        var rx = R * p.s, ry = rx * eAt(y, p.D);
        var a0 = 0, a1 = Math.PI * 2;
        if (part === 'back') { a0 = Math.PI; a1 = Math.PI * 2; }
        if (part === 'front') { a0 = 0; a1 = Math.PI; }
        var style = ringStyle(c, p.x, rx, skinId);
        var lw = Math.max(2, THICK * 2.2 * p.s);
        c.save();
        c.lineCap = 'round';
        c.beginPath();
        c.ellipse(p.x, p.y, rx, ry, 0, a0, a1);
        c.strokeStyle = style.dark;
        c.lineWidth = lw;
        c.stroke();
        c.beginPath();
        c.ellipse(p.x, p.y - lw * 0.18, rx, ry, 0, a0, a1);
        c.strokeStyle = style.light;
        c.lineWidth = lw * 0.5;
        c.stroke();
        if (part !== 'back') {
            var a = (spin || 0) % (Math.PI * 2);
            if (part === 'all' || (a > 0 && a < Math.PI)) {
                c.fillStyle = 'rgba(255, 255, 255, 0.85)';
                c.beginPath();
                c.arc(p.x + Math.cos(a) * rx, p.y + Math.sin(a) * ry - lw * 0.2, lw * 0.22, 0, Math.PI * 2);
                c.fill();
            }
        }
        c.restore();
    }

    function drawShadow(x, z, r, alpha) {
        var p = project(x, 0, z);
        ctx.fillStyle = 'rgba(0, 0, 0, ' + alpha + ')';
        ctx.beginPath();
        ctx.ellipse(p.x, p.y, r * p.s, r * p.s * eAt(0, p.D), 0, 0, Math.PI * 2);
        ctx.fill();
    }

    // --- Sound -------------------------------------------------------------------------
    var audio = null;
    var SOUNDS = {
        toss: [[420, 0.07, 'sine', 0.035, 0]],
        clink: [[2300, 0.06, 'triangle', 0.07, 0], [3200, 0.05, 'triangle', 0.045, 0.03]],
        thud: [[130, 0.14, 'sine', 0.12, 0]],
        ding: [[880, 0.14, 'sine', 0.1, 0], [1320, 0.22, 'sine', 0.09, 0.07]],
        streak: [[880, 0.1, 'triangle', 0.06, 0], [1175, 0.1, 'triangle', 0.06, 0.07], [1568, 0.22, 'triangle', 0.06, 0.14]],
        miss: [[300, 0.14, 'sine', 0.05, 0], [215, 0.2, 'sine', 0.045, 0.09]],
        unlock: [[660, 0.1, 'square', 0.035, 0], [880, 0.1, 'square', 0.035, 0.1], [1175, 0.1, 'square', 0.035, 0.2], [1568, 0.3, 'square', 0.035, 0.3]],
        buy: [[1046, 0.08, 'triangle', 0.05, 0], [1568, 0.14, 'triangle', 0.05, 0.06]]
    };

    function sfx(name) {
        if (!state.sound) return;
        try {
            audio = audio || new (window.AudioContext || window.webkitAudioContext)();
            if (audio.state === 'suspended') audio.resume();
            SOUNDS[name].forEach(function (n) {
                var t = audio.currentTime + n[4];
                var osc = audio.createOscillator();
                var gain = audio.createGain();
                osc.type = n[2];
                osc.frequency.setValueAtTime(n[0], t);
                gain.gain.setValueAtTime(n[3], t);
                gain.gain.exponentialRampToValueAtTime(0.0001, t + n[1]);
                osc.connect(gain);
                gain.connect(audio.destination);
                osc.start(t);
                osc.stop(t + n[1] + 0.02);
            });
        } catch (err) {
            // No Web Audio: play silently.
        }
    }

    // --- Game state ----------------------------------------------------------------------
    var game = {
        phase: 'title', score: 0, streak: 0, ringsLeft: 10, throws: 0,
        hats: [], ring: null, aim: null, texts: [], sparks: [], banner: null,
        timer: 0, after: null, unlockedThisRound: [], gearsThisRound: 0, roundBestStreak: 0, now: 0
    };
    var keyAim = { power: 0.45, aim: 0 };

    function pool() {
        return HATS.filter(function (h) { return state.unlocked.indexOf(h.id) !== -1; });
    }

    function pickHat(avoid) {
        var choices = pool().filter(function (h) { return avoid.indexOf(h.id) === -1; });
        if (!choices.length) choices = pool();
        // Newer hats turn up a little more often than the starter.
        var weights = choices.map(function (h, i) { return 1 + i * 0.35; });
        var total = weights.reduce(function (a, b) { return a + b; }, 0);
        var roll = Math.random() * total;
        for (var i = 0; i < choices.length; i++) {
            roll -= weights[i];
            if (roll <= 0) return choices[i];
        }
        return choices[choices.length - 1];
    }

    function placeHat(slot) {
        var band = BANDS[slot];
        var z = rand(band[0], band[1]);
        var spread = 0.5 + z * 0.17;
        var x = 0;
        for (var tries = 0; tries < 12; tries++) {
            x = rand(-spread, spread);
            var clear = game.hats.every(function (o) { return !o || o.slot === slot || Math.abs(o.x - x) > 0.75; });
            if (clear) break;
        }
        var avoid = game.hats.filter(function (o) { return o && o.slot !== slot; }).map(function (o) { return o.def.id; });
        game.hats[slot] = { slot: slot, def: pickHat(avoid), x: x, z: z, born: game.now, ring: null };
    }

    function setField() {
        game.hats = [];
        for (var i = 0; i < BANDS.length; i++) placeHat(i);
    }


    function startRound() {
        game.score = 0;
        game.streak = 0;
        game.throws = 0;
        game.ringsLeft = upgrade('bag');
        game.ring = null;
        game.unlockedThisRound = [];
        game.gearsThisRound = 0;
        game.roundBestStreak = 0;
        game.banner = null;
        setField();
        game.phase = 'aim';
        showOverlay(null);
        hud();
        canvas.focus({ preventScroll: true });
    }

    function launchVelocity(power, aim) {
        var v = 5 + power * 5.2;
        return { vx: aim * 2.6, vy: v * Math.sin(LAUNCH_ANGLE), vz: v * Math.cos(LAUNCH_ANGLE) };
    }

    function flightTime(vy, height) {
        var disc = vy * vy + 2 * G * (HAND.y - height);
        return disc < 0 ? NaN : (vy + Math.sqrt(disc)) / G;
    }

    // Find the hat this throw comes closest to and bend the throw toward its
    // tip. Close throws are pulled nearly all the way on; wide ones only get a
    // nudge, and every throw keeps a little wobble, so it is easy but never
    // automatic.
    function aimAssist(vel) {
        var best = null, bestD = ASSIST_RANGE, bestT = 0;
        game.hats.forEach(function (hat) {
            if (!hat) return;
            var T = flightTime(vel.vy, hat.def.h);
            if (!(T > 0)) return;
            var dx = HAND.x + vel.vx * T - hat.x, dz = HAND.z + vel.vz * T - hat.z;
            var d = Math.sqrt(dx * dx + dz * dz);
            if (d < bestD) { best = hat; bestD = d; bestT = T; }
        });
        if (!best) return vel;
        var pull = clamp(1.15 - bestD / ASSIST_RANGE, 0, ASSIST_PULL);
        var x = HAND.x + vel.vx * bestT, z = HAND.z + vel.vz * bestT;
        x += (best.x - x) * pull + rand(-WOBBLE, WOBBLE);
        z += (best.z - z) * pull + rand(-WOBBLE, WOBBLE);
        return { vx: (x - HAND.x) / bestT, vy: vel.vy, vz: (z - HAND.z) / bestT };
    }

    function throwRing(power, aim) {
        if (game.phase !== 'aim' || game.ringsLeft <= 0) return;
        var vel = aimAssist(launchVelocity(power, aim));
        game.ring = {
            x: HAND.x, y: HAND.y, z: HAND.z, vx: vel.vx, vy: vel.vy, vz: vel.vz,
            R: upgrade('ring'), spin: 0, age: 0, threaded: null, bounced: false, swish: false,
            floorHits: 0, cool: 0, state: 'fly'
        };
        game.ringsLeft -= 1;
        game.throws += 1;
        game.phase = 'flight';
        game.aim = null;
        sfx('toss');
        hud();
    }

    // --- Physics -------------------------------------------------------------------------
    function stepRing(r, dt) {
        var px = r.x, py = r.y, pz = r.z;
        r.age += dt;
        r.spin += dt * 9;
        r.cool = Math.max(0, r.cool - dt);
        if (r.y > 0) r.vy -= G * dt;
        r.x += r.vx * dt;
        r.y += r.vy * dt;
        r.z += r.vz * dt;

        for (var i = 0; i < game.hats.length; i++) {
            var hat = game.hats[i];
            if (!hat) continue;
            var def = hat.def, top = def.h;
            var dx = r.x - hat.x, dz = r.z - hat.z, d = Math.sqrt(dx * dx + dz * dz);

            // Coming down past the tip: did the ring go over it?
            if (!r.threaded && py >= top && r.y < top) {
                var t = (py - top) / ((py - r.y) || 1);
                var cx = px + (r.x - px) * t - hat.x, cz = pz + (r.z - pz) * t - hat.z;
                var cd = Math.sqrt(cx * cx + cz * cz);
                if (cd < r.R - radiusAt(def, top * 0.97) - THICK) {
                    r.threaded = hat;
                    r.swish = cd < r.R * 0.3 && !r.bounced;
                }
            }

            if (r.y < top && r.cool <= 0) {
                var rr = radiusAt(def, Math.max(0, r.y));
                if (r.threaded === hat) {
                    if (d + rr >= r.R - THICK) { settle(r, hat); return; }
                } else if (!r.threaded && d <= r.R + rr + THICK && d >= r.R - rr - THICK) {
                    rimHit(r, hat, dx, dz, d, rr);
                }
            }
        }

        if (r.z > WALL_Z && r.vz > 0) {
            r.z = WALL_Z;
            r.vz = -Math.abs(r.vz) * 0.35;
            r.vx *= 0.6;
            sfx('thud');
        }
        if (Math.abs(r.x) > FIELD_X) {
            r.x = clamp(r.x, -FIELD_X, FIELD_X);
            r.vx = -r.vx * 0.35;
        }

        if (r.y <= 0) {
            r.y = 0;
            if (r.vy < -1.4 && r.floorHits < 2) {
                r.vy = -r.vy * 0.22;
                r.vx *= 0.5;
                r.vz *= 0.5;
                r.floorHits += 1;
                sfx('thud');
            } else {
                r.vy = 0;
                var drag = Math.pow(0.015, dt);
                r.vx *= drag;
                r.vz *= drag;
                if (Math.abs(r.vx) + Math.abs(r.vz) < 0.06) { landed(r); return; }
            }
        }
        if (r.age > 6) landed(r);
    }

    function rimHit(r, hat, dx, dz, d, rr) {
        r.bounced = true;
        r.cool = 0.09;
        sfx('clink');
        var nx = d > 1e-4 ? dx / d : 0, nz = d > 1e-4 ? dz / d : -1;
        if (Math.random() < 0.45) {
            // Rattles around the tip and drops on.
            r.threaded = hat;
            say('Rattled in!', r, '#ffe066', 13);
            return;
        }
        var vn = r.vx * nx + r.vz * nz;
        var push = Math.max(0.9, -vn * 0.6);
        r.vx = (r.vx - vn * nx) * 0.55 + nx * push;
        r.vz = (r.vz - vn * nz) * 0.55 + nz * push;
        r.vy = Math.abs(r.vy) * 0.25;
        r.spin += 3;
    }

    function settle(r, hat) {
        r.state = 'settle';
        r.from = { x: r.x, y: r.y, z: r.z };
        r.to = { x: hat.x + rand(-0.02, 0.02), y: restHeight(hat.def, r.R), z: hat.z + rand(-0.02, 0.02) };
        r.t = 0;
        hat.ring = r;
        game.ring = null;
        scoreRinger(hat, r);
    }

    function landed(r) {
        if (r.state !== 'fly') return;
        r.state = 'ground';
        var leaner = game.hats.some(function (hat) {
            if (!hat) return false;
            var d = Math.sqrt(Math.pow(r.x - hat.x, 2) + Math.pow(r.z - hat.z, 2));
            return d < r.R + radiusAt(hat.def, 0) + 0.07;
        });
        resolveMiss(r, leaner);
    }

    // --- Scoring -------------------------------------------------------------------------
    function scoreRinger(hat, r) {
        game.streak += 1;
        game.roundBestStreak = Math.max(game.roundBestStreak, game.streak);
        var mult = Math.min(5, game.streak);
        var base = hat.def.pts + Math.round(hat.z * 2);
        var tags = [];
        if (r.bounced) { base = Math.round(base * 1.5); tags.push('Bank shot'); }
        if (r.swish) { base += 5; tags.push('Swish'); }
        var pts = base * mult;
        var gears = 1 + upgrade('gearbox') + (game.streak >= 3 ? 1 : 0) + (game.streak >= 6 ? 1 : 0);

        game.score += pts;
        game.gearsThisRound += gears;
        state.gears += gears;
        state.ringers += 1;
        state.rung[hat.def.id] = (state.rung[hat.def.id] || 0) + 1;
        state.bestStreak = Math.max(state.bestStreak, game.streak);
        addLifetime(pts);

        var at = project(hat.x, hat.def.h + 0.1, hat.z);
        say('+' + fmt(pts), { sx: at.x, sy: at.y - 6 }, '#ffe066', 22);
        say(hat.def.name + (mult > 1 ? '  ×' + mult : ''), { sx: at.x, sy: at.y + 14 }, '#ffffff', 13);
        if (tags.length) say(tags.join(' + '), { sx: at.x, sy: at.y + 32 }, '#7fe7e2', 12);
        burst(at.x, at.y + 10, game.streak >= 3 ? 26 : 14);
        sfx(game.streak >= 3 ? 'streak' : 'ding');
        if (game.streak === 3 || game.streak === 5 || game.streak === 8) {
            game.banner = { text: game.streak + ' in a row!', sub: game.streak >= 5 ? 'Max multiplier' : '×' + mult + ' points', t: 0, life: 1.6 };
        }
        game.phase = 'result';
        game.timer = 1.15;
        game.after = function () { afterThrow(hat.slot); };
        saveState();
        hud();
    }

    function resolveMiss(r, leaner) {
        var at = project(r.x, 0.3, r.z);
        if (leaner) {
            game.score += 2;
            addLifetime(2);
            say('Leaner +2', { sx: at.x, sy: at.y }, '#f1f1f1', 14);
        } else {
            say('Miss', { sx: at.x, sy: at.y }, 'rgba(255, 255, 255, 0.7)', 14);
        }
        if (game.streak >= 2 && state.saves > 0) {
            state.saves -= 1;
            say('Streak saved!', { sx: view.W / 2, sy: view.H * 0.3 }, '#7dffb3', 16);
        } else {
            if (game.streak >= 3) say('Streak over', { sx: view.W / 2, sy: view.H * 0.3 }, '#ff9a9a', 14);
            game.streak = 0;
        }
        sfx('miss');
        game.phase = 'result';
        game.timer = 0.85;
        game.after = function () { afterThrow(-1); };
        saveState();
        hud();
    }

    function addLifetime(pts) {
        state.lifetime += pts;
        HATS.forEach(function (h) {
            if (h.unlock <= state.lifetime && state.unlocked.indexOf(h.id) === -1) {
                state.unlocked.push(h.id);
                game.unlockedThisRound.push(h.id);
                game.banner = { text: 'New hat: ' + h.name, sub: h.origin + ', ' + h.era, t: 0, life: 2.6, hat: h };
                sfx('unlock');
                renderMuseum();
                renderShop();
            }
        });
    }

    function afterThrow(slot) {
        var old = game.ring;
        game.ring = null;
        if (old) old.state = 'gone';
        if (slot >= 0) placeHat(slot);
        if (game.ringsLeft <= 0) { endRound(); return; }
        game.phase = 'aim';
        hud();
    }

    function endRound() {
        var bonus = Math.floor(game.score / 50);
        state.gears += bonus;
        game.gearsThisRound += bonus;
        state.rounds += 1;
        var newBest = game.score > state.best;
        if (newBest) state.best = game.score;
        saveState();
        game.phase = 'over';
        hud();
        showOverlay('over', { newBest: newBest, bonus: bonus });
    }

    // --- Effects -------------------------------------------------------------------------
    function say(text, at, color, size) {
        var x = at.sx, y = at.sy;
        if (x === undefined) { var p = project(at.x, at.y + 0.3, at.z); x = p.x; y = p.y; }
        game.texts.push({ text: text, x: x, y: y, color: color, size: size, t: 0, life: 1.3 });
    }

    function burst(x, y, n) {
        if (reduceMotion) return;
        var colors = ['#ffe066', '#ffd700', '#ffffff', '#c8676a'];
        for (var i = 0; i < n; i++) {
            var a = rand(0, Math.PI * 2), sp = rand(60, 220);
            game.sparks.push({ x: x, y: y, vx: Math.cos(a) * sp, vy: Math.sin(a) * sp - 80, t: 0, life: rand(0.5, 0.9), color: colors[i % colors.length], size: rand(2, 4) });
        }
    }

    // --- Input ---------------------------------------------------------------------------
    function maxDrag() { return clamp(view.H * 0.6, 170, 320); }

    function aimFrom(dx, dy) {
        return { power: clamp(dy / maxDrag(), 0, 1), aim: clamp(-dx / (view.W * 0.38), -1, 1), dx: dx, dy: dy };
    }

    canvas.addEventListener('pointerdown', function (e) {
        if (game.phase !== 'aim') return;
        e.preventDefault();
        try { canvas.setPointerCapture(e.pointerId); } catch (err) { /* older browsers */ }
        game.aim = { id: e.pointerId, x0: e.clientX, y0: e.clientY, power: 0, aim: 0, dx: 0, dy: 0 };
    });
    canvas.addEventListener('pointermove', function (e) {
        if (!game.aim || game.aim.id !== e.pointerId) return;
        var a = aimFrom(e.clientX - game.aim.x0, e.clientY - game.aim.y0);
        game.aim.power = a.power; game.aim.aim = a.aim; game.aim.dx = a.dx; game.aim.dy = a.dy;
    });
    canvas.addEventListener('pointerup', function (e) {
        if (!game.aim || game.aim.id !== e.pointerId) return;
        var a = game.aim;
        game.aim = null;
        if (a.power >= 0.06) throwRing(a.power, a.aim);
    });
    canvas.addEventListener('pointercancel', function () { game.aim = null; });

    canvas.addEventListener('keydown', function (e) {
        if (game.phase !== 'aim') {
            if ((e.key === 'Enter' || e.key === ' ') && (game.phase === 'title' || game.phase === 'over')) {
                e.preventDefault();
                startRound();
            }
            return;
        }
        var handled = true;
        if (e.key === 'ArrowLeft') keyAim.aim = clamp(keyAim.aim - 0.03, -1, 1);
        else if (e.key === 'ArrowRight') keyAim.aim = clamp(keyAim.aim + 0.03, -1, 1);
        else if (e.key === 'ArrowUp') keyAim.power = clamp(keyAim.power + 0.015, 0.06, 1);
        else if (e.key === 'ArrowDown') keyAim.power = clamp(keyAim.power - 0.015, 0.06, 1);
        else if (e.key === ' ' || e.key === 'Enter') { throwRing(keyAim.power, keyAim.aim); game.keyAiming = false; }
        else handled = false;
        if (handled) {
            e.preventDefault();
            if (game.phase === 'aim') game.keyAiming = true;
        }
    });
    canvas.addEventListener('blur', function () { game.keyAiming = false; });

    // --- Main loop -----------------------------------------------------------------------
    var last = 0;

    function frame(ms) {
        var dt = last ? Math.min(0.05, (ms - last) / 1000) : 0;
        last = ms;
        game.now += dt;
        update(dt);
        render();
        window.requestAnimationFrame(frame);
    }

    function update(dt) {
        if (game.ring && game.ring.state === 'fly') {
            var steps = Math.ceil(dt / (1 / 240));
            for (var i = 0; i < steps && game.ring && game.ring.state === 'fly'; i++) stepRing(game.ring, dt / steps);
        }
        game.hats.forEach(function (hat) {
            var r = hat && hat.ring;
            if (!r || r.state !== 'settle') return;
            r.t = Math.min(1, r.t + dt / 0.4);
            var e = easeOut(r.t);
            r.x = r.from.x + (r.to.x - r.from.x) * e;
            r.z = r.from.z + (r.to.z - r.from.z) * e;
            r.y = r.from.y + (r.to.y - r.from.y) * e;
            if (!reduceMotion && r.t < 1) r.y += Math.sin(r.t * Math.PI * 3) * 0.02 * (1 - r.t);
            r.spin += dt * 6 * (1 - r.t);
        });
        if (game.phase === 'result') {
            game.timer -= dt;
            if (game.timer <= 0 && game.after) { var go = game.after; game.after = null; go(); }
        }
        game.texts = game.texts.filter(function (t) { t.t += dt; t.y -= dt * 28; return t.t < t.life; });
        game.sparks = game.sparks.filter(function (s) {
            s.t += dt; s.x += s.vx * dt; s.y += s.vy * dt; s.vy += 420 * dt;
            return s.t < s.life;
        });
        if (game.banner) {
            game.banner.t += dt;
            if (game.banner.t > game.banner.life) game.banner = null;
        }
    }

    // --- Render --------------------------------------------------------------------------
    function render() {
        var W = view.W, H = view.H;
        ctx.clearRect(0, 0, W, H);
        drawBackdrop(W, H);
        drawFloor();
        drawWall();

        game.hats.forEach(function (hat) {
            if (hat) drawShadow(hat.x, hat.z, radiusAt(hat.def, 0) * 1.15, 0.35);
        });
        var fly = game.ring;
        if (fly) drawShadow(fly.x, fly.z, fly.R, 0.28 * (1 - Math.min(1, fly.y / 3)));

        var items = [];
        game.hats.forEach(function (hat) { if (hat) items.push({ z: hat.z, hat: hat }); });
        if (fly) items.push({ z: fly.z, ring: fly });
        items.sort(function (a, b) { return b.z - a.z; });
        items.forEach(function (it) {
            if (it.hat) drawFieldHat(it.hat);
            else drawRing(ctx, it.ring.x, it.ring.y, it.ring.z, it.ring.R, 'all', it.ring.spin, state.skin);
        });

        if (game.phase === 'aim' || game.phase === 'title') drawHand();
        drawEffects();
    }

    function drawBackdrop(W, H) {
        var g = ctx.createRadialGradient(W / 2, view.horizon, 10, W / 2, view.horizon, Math.max(W, H));
        g.addColorStop(0, '#3a0606');
        g.addColorStop(0.55, '#170202');
        g.addColorStop(1, '#050000');
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, W, H);
    }

    function drawFloor() {
        var zNear = 0.55;
        var a = project(-FIELD_X, 0, zNear), b = project(FIELD_X, 0, zNear);
        var c = project(FIELD_X, 0, WALL_Z), d = project(-FIELD_X, 0, WALL_Z);
        var g = ctx.createLinearGradient(0, d.y, 0, view.H);
        g.addColorStop(0, '#202024');
        g.addColorStop(1, '#3a3a40');
        ctx.fillStyle = g;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.lineTo(c.x, c.y); ctx.lineTo(d.x, d.y);
        ctx.closePath();
        ctx.fill();
        ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (var x = -FIELD_X; x <= FIELD_X + 0.01; x += TILE) {
            var p0 = project(x, 0, zNear), p1 = project(x, 0, WALL_Z);
            ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y);
        }
        for (var z = WALL_Z; z > zNear; z -= TILE) {
            var q0 = project(-FIELD_X, 0, z), q1 = project(FIELD_X, 0, z);
            ctx.moveTo(q0.x, q0.y); ctx.lineTo(q1.x, q1.y);
        }
        ctx.stroke();
        // Fade the floor's edges into the dark.
        var side = ctx.createLinearGradient(0, 0, view.W, 0);
        side.addColorStop(0, 'rgba(5, 0, 0, 0.75)');
        side.addColorStop(0.18, 'rgba(5, 0, 0, 0)');
        side.addColorStop(0.82, 'rgba(5, 0, 0, 0)');
        side.addColorStop(1, 'rgba(5, 0, 0, 0.75)');
        ctx.fillStyle = side;
        ctx.fillRect(0, d.y, view.W, view.H - d.y);
    }

    function drawWall() {
        var h = 0.32;
        var a = project(-FIELD_X, 0, WALL_Z), b = project(FIELD_X, 0, WALL_Z);
        var top = project(0, h, WALL_Z).y;
        ctx.fillStyle = '#5e0000';
        ctx.fillRect(a.x, top, b.x - a.x, a.y - top);
        ctx.fillStyle = '#944547';
        ctx.fillRect(a.x, top, b.x - a.x, Math.max(2, (a.y - top) * 0.18));
        var mid = project(0, h * 0.42, WALL_Z);
        ctx.fillStyle = 'rgba(255, 215, 0, 0.55)';
        ctx.font = '700 ' + Math.max(8, Math.round(mid.s * 0.16)) + 'px "Space Mono", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('MEPHAM ROBOTICS', mid.x, mid.y);
    }

    function drawFieldHat(hat) {
        var p = project(hat.x, 0, hat.z);
        var grow = reduceMotion ? 1 : easeOut(clamp((game.now - hat.born) / 0.35, 0, 1));
        var r = hat.ring;
        if (r) drawRing(ctx, r.x, r.y, r.z, r.R, 'back', r.spin, state.skin);
        ctx.save();
        if (grow < 1) {
            ctx.translate(p.x, p.y);
            ctx.scale(grow, grow);
            ctx.translate(-p.x, -p.y);
        }
        drawHat(ctx, hat.def, { sx: p.x, sy: p.y, s: p.s, D: p.D });
        ctx.restore();
        if (r) drawRing(ctx, r.x, r.y, r.z, r.R, 'front', r.spin, state.skin);
    }

    function currentAim() {
        if (game.aim) return game.aim;
        if (game.keyAiming) return { power: keyAim.power, aim: keyAim.aim, dx: -keyAim.aim * view.W * 0.38, dy: keyAim.power * maxDrag() };
        return null;
    }

    function drawHand() {
        var a = currentAim();
        var R = upgrade('ring');
        if (a && a.power > 0.02) drawGuide(a);
        var p = project(HAND.x, HAND.y, HAND.z);
        var bob = reduceMotion || a ? 0 : Math.sin(game.now * 2.4) * 4;
        var ox = a ? a.dx * 0.18 : 0, oy = a ? Math.min(a.dy, maxDrag()) * 0.18 : 0;
        if (a) {
            ctx.strokeStyle = 'rgba(255, 215, 0, 0.35)';
            ctx.lineWidth = 2;
            ctx.setLineDash([4, 6]);
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p.x + ox, p.y + oy);
            ctx.stroke();
            ctx.setLineDash([]);
        }
        ctx.save();
        ctx.translate(ox, oy + bob);
        drawRing(ctx, HAND.x, HAND.y, HAND.z, Math.min(R, 0.32), 'all', game.now * 0.8, state.skin);
        ctx.restore();
        if (a) {
            // Power meter beside the ring.
            var x = Math.min(view.W - 18, p.x + R * p.s + 22), h = 90, y = p.y - h / 2;
            ctx.fillStyle = 'rgba(255, 255, 255, 0.12)';
            ctx.fillRect(x, y, 8, h);
            ctx.fillStyle = a.power > 0.85 ? '#ff7b7b' : '#ffd700';
            ctx.fillRect(x, y + h * (1 - a.power), 8, h * a.power);
        } else if (game.phase === 'aim' && game.throws === 0 && game.ringsLeft > 0) {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.75)';
            ctx.font = '700 14px "Balsamiq Sans", cursive';
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText('Pull down, aim, let go', view.W / 2, Math.min(view.H - 16, p.y + R * p.s * 0.8 + 26));
        }
    }

    function drawGuide(a) {
        var v = launchVelocity(a.power, a.aim);
        var T = (v.vy + Math.sqrt(v.vy * v.vy + 2 * G * (HAND.y - 0.6))) / G;
        var until = T * upgrade('guide');
        for (var t = 0.06; t < until; t += 0.06) {
            var x = HAND.x + v.vx * t, y = HAND.y + v.vy * t - 0.5 * G * t * t, z = HAND.z + v.vz * t;
            var p = project(x, y, z);
            var fade = 1 - t / until;
            ctx.fillStyle = 'rgba(255, 215, 0, ' + (0.15 + 0.6 * fade).toFixed(3) + ')';
            ctx.beginPath();
            ctx.arc(p.x, p.y, clamp(0.025 * p.s, 1.5, 5), 0, Math.PI * 2);
            ctx.fill();
        }
    }


    function drawEffects() {
        game.sparks.forEach(function (s) {
            ctx.globalAlpha = 1 - s.t / s.life;
            ctx.fillStyle = s.color;
            ctx.fillRect(s.x, s.y, s.size, s.size);
        });
        ctx.globalAlpha = 1;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        game.texts.forEach(function (t) {
            ctx.globalAlpha = clamp(1.4 - t.t / t.life * 1.4, 0, 1);
            ctx.font = '700 ' + t.size + 'px "Balsamiq Sans", cursive';
            ctx.lineWidth = 4;
            ctx.strokeStyle = 'rgba(0, 0, 0, 0.6)';
            ctx.strokeText(t.text, t.x, t.y);
            ctx.fillStyle = t.color;
            ctx.fillText(t.text, t.x, t.y);
        });
        ctx.globalAlpha = 1;
        var b = game.banner;
        if (b) {
            var k = reduceMotion ? 1 : easeOut(clamp(b.t / 0.25, 0, 1));
            var fade = clamp((b.life - b.t) / 0.4, 0, 1);
            var y = view.H * 0.2;
            ctx.globalAlpha = fade;
            ctx.fillStyle = 'rgba(20, 0, 0, 0.8)';
            var w = Math.min(view.W - 32, 340), h = b.hat ? 92 : 60;
            ctx.save();
            ctx.translate(view.W / 2, y);
            ctx.scale(k, k);
            ctx.beginPath();
            ctx.roundRect ? ctx.roundRect(-w / 2, -h / 2, w, h, 14) : ctx.rect(-w / 2, -h / 2, w, h);
            ctx.fill();
            ctx.strokeStyle = 'rgba(255, 215, 0, 0.6)';
            ctx.lineWidth = 1.5;
            ctx.stroke();
            var textX = 0;
            if (b.hat) {
                drawHat(ctx, b.hat, { sx: -w / 2 + 44, sy: h / 2 - 16, s: 62 / Math.max(b.hat.h, 0.8), D: 3.4 });
                textX = 30;
            }
            ctx.fillStyle = '#ffd700';
            ctx.font = '700 18px "Balsamiq Sans", cursive';
            ctx.fillText(b.text, textX, b.sub ? -9 : 0, w - (b.hat ? 96 : 24));
            if (b.sub) {
                ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
                ctx.font = '13px "Balsamiq Sans", cursive';
                ctx.fillText(b.sub, textX, 14, w - (b.hat ? 96 : 24));
            }
            ctx.restore();
            ctx.globalAlpha = 1;
        }
    }

    // --- Sizing --------------------------------------------------------------------------
    function resize() {
        var rect = canvas.getBoundingClientRect();
        var dpr = Math.min(2, window.devicePixelRatio || 1);
        view.W = Math.max(280, rect.width);
        view.H = Math.max(300, rect.height);
        view.F = view.H * 1.05;
        view.horizon = view.H * 0.14;
        canvas.width = Math.round(view.W * dpr);
        canvas.height = Math.round(view.H * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    if (window.ResizeObserver) new ResizeObserver(resize).observe(canvas);
    else window.addEventListener('resize', resize);

    // --- HUD and panels ------------------------------------------------------------------
    function el(name) { return root.querySelector('[data-ht="' + name + '"]'); }

    function hud() {
        el('score').textContent = fmt(game.score);
        el('best').textContent = fmt(Math.max(state.best, game.score));
        el('streak').textContent = game.streak;
        el('mult').textContent = '×' + Math.max(1, Math.min(5, game.streak));
        el('rings').textContent = game.ringsLeft;
        el('gears').textContent = fmt(state.gears);
        el('saves').textContent = state.saves;
        root.querySelector('[data-ht-streak]').classList.toggle('is-hot', game.streak >= 3);
        var next = HATS.filter(function (h) { return state.unlocked.indexOf(h.id) === -1; })[0];
        var prev = HATS.filter(function (h) { return state.unlocked.indexOf(h.id) !== -1; }).pop();
        if (next) {
            var from = prev ? prev.unlock : 0;
            el('next').textContent = 'Next hat unlocks in ' + fmt(next.unlock - state.lifetime) + ' points';
            el('bar').style.width = clamp((state.lifetime - from) / ((next.unlock - from) || 1), 0, 1) * 100 + '%';
        } else {
            el('next').textContent = 'Every hat unlocked. Certified hat historian.';
            el('bar').style.width = '100%';
        }
        el('lifetime').textContent = fmt(state.lifetime);
        var fresh = state.unlocked.filter(function (id) { return state.seen.indexOf(id) === -1; }).length;
        var badge = el('new');
        badge.textContent = fresh;
        badge.hidden = !fresh;
        var sound = root.querySelector('[data-ht-sound]');
        sound.setAttribute('aria-pressed', state.sound ? 'true' : 'false');
        sound.querySelector('span').textContent = state.sound ? 'Sound on' : 'Sound off';
    }

    var overlay = root.querySelector('[data-ht-overlay]');

    function showOverlay(kind, info) {
        if (!kind) { overlay.hidden = true; return; }
        overlay.hidden = false;
        if (kind === 'title') {
            overlay.innerHTML =
                '<div class="ht-card">' +
                '<p class="ht-kicker">404 bonus round</p>' +
                '<h2 class="ht-card-title">Hat Toss</h2>' +
                '<p>Every peg is a pointed hat from a famous head in history, or a cone from a robotics game. Pull down and let go to drop a hoop over its tip.</p>' +
                '<ul class="ht-rules">' +
                '<li>Ring hats in a row for up to <strong>×5</strong> points.</li>' +
                '<li>Points unlock new hats. Gears buy upgrades.</li>' +
                '<li>Get close and the hoop drifts toward the nearest tip.</li>' +
                '</ul>' +
                '<button type="button" class="cta-button cta-primary" data-ht-action="start">Start throwing</button>' +
                '<p class="ht-keys">Keyboard: arrows to aim, Space to throw.</p>' +
                '</div>';
        } else {
            var unlocked = game.unlockedThisRound.map(function (id) { return HAT_BY_ID[id].name; });
            overlay.innerHTML =
                '<div class="ht-card">' +
                '<p class="ht-kicker">' + (info.newBest ? 'New best!' : 'Round over') + '</p>' +
                '<p class="ht-final">' + fmt(game.score) + '<span>points</span></p>' +
                '<dl class="ht-summary">' +
                '<div><dt>Best streak</dt><dd>' + game.roundBestStreak + '</dd></div>' +
                '<div><dt>Gears earned</dt><dd>' + game.gearsThisRound + '</dd></div>' +
                '<div><dt>Best ever</dt><dd>' + fmt(state.best) + '</dd></div>' +
                '</dl>' +
                (unlocked.length ? '<p class="ht-unlocked">Unlocked: ' + unlocked.join(', ') + '</p>' : '') +
                '<div class="ht-card-actions">' +
                '<button type="button" class="cta-button cta-primary" data-ht-action="start">Play again</button>' +
                '<button type="button" class="cta-button cta-secondary" data-ht-action="shop">Spend gears</button>' +
                '</div>' +
                '</div>';
        }
    }

    function renderMuseum() {
        var grid = root.querySelector('[data-ht-museum]');
        grid.innerHTML = HATS.map(function (h) {
            var open = state.unlocked.indexOf(h.id) !== -1;
            var fresh = open && state.seen.indexOf(h.id) === -1;
            var rung = state.rung[h.id] || 0;
            return '<article class="ht-hat' + (open ? '' : ' is-locked') + '">' +
                '<canvas class="ht-hat-art" width="160" height="150" data-ht-thumb="' + h.id + '" aria-hidden="true"></canvas>' +
                '<div class="ht-hat-body">' +
                '<h3>' + (open ? h.name : 'Locked hat') + (fresh ? ' <span class="ht-pill">New</span>' : '') + '</h3>' +
                (open
                    ? '<p class="ht-hat-meta">' + h.origin + ' · ' + h.era + ' · ' + h.pts + ' pts</p><p>' + h.fact + '</p>' +
                      '<p class="ht-hat-meta">Rung ' + rung + (rung === 1 ? ' time' : ' times') + '</p>'
                    : '<p class="ht-hat-meta">Unlocks at ' + fmt(h.unlock) + ' lifetime points</p>') +
                '</div></article>';
        }).join('');
        grid.querySelectorAll('[data-ht-thumb]').forEach(function (cv) {
            var def = HAT_BY_ID[cv.getAttribute('data-ht-thumb')];
            var c = cv.getContext('2d');
            var dpr = Math.min(2, window.devicePixelRatio || 1);
            cv.width = 160 * dpr;
            cv.height = 150 * dpr;
            c.setTransform(dpr, 0, 0, dpr, 0, 0);
            var wide = Math.max.apply(null, def.profile.map(function (q) { return q[1]; }));
            var s = Math.min(112 / def.h, 62 / wide);
            c.fillStyle = 'rgba(0, 0, 0, 0.35)';
            c.beginPath();
            c.ellipse(80, 134, wide * s * 1.1, wide * s * 0.28, 0, 0, Math.PI * 2);
            c.fill();
            drawHat(c, def, { sx: 80, sy: 134, s: s, D: 3.4 }, state.unlocked.indexOf(def.id) === -1);
        });
    }

    function renderShop() {
        var box = root.querySelector('[data-ht-shop]');
        var cards = UPGRADES.map(function (u) {
            var level = state.up[u.id], maxed = level >= u.costs.length;
            var cost = maxed ? 0 : u.costs[level];
            var pips = '';
            for (var i = 0; i < u.costs.length; i++) pips += '<span class="ht-pip' + (i < level ? ' is-on' : '') + '"></span>';
            return '<div class="ht-item">' +
                '<div><h3>' + u.name + '</h3><p>' + u.blurb + '</p><div class="ht-pips" aria-label="Level ' + level + ' of ' + u.costs.length + '">' + pips + '</div></div>' +
                (maxed
                    ? '<span class="ht-maxed">Maxed</span>'
                    : '<button type="button" class="ht-buy" data-ht-buy="' + u.id + '"' + (state.gears < cost ? ' disabled' : '') + '>' + cost + ' gears</button>') +
                '</div>';
        });
        cards.push('<div class="ht-item">' +
            '<div><h3>Streak saver</h3><p>Forgives one miss when you are on a streak of 2 or more. Holds up to ' + SAVER.max + '.</p>' +
            '<p class="ht-hat-meta">Holding ' + state.saves + '</p></div>' +
            (state.saves >= SAVER.max
                ? '<span class="ht-maxed">Full</span>'
                : '<button type="button" class="ht-buy" data-ht-buy="saver"' + (state.gears < SAVER.cost ? ' disabled' : '') + '>' + SAVER.cost + ' gears</button>') +
            '</div>');
        var skins = SKINS.map(function (s) {
            var owned = state.skins.indexOf(s.id) !== -1, on = state.skin === s.id;
            var label = on ? 'Equipped' : owned ? 'Equip' : s.cost + ' gears';
            return '<button type="button" class="ht-skin' + (on ? ' is-on' : '') + (s.colors ? '' : ' is-rainbow') + '" data-ht-skin="' + s.id + '"' +
                (!owned && state.gears < s.cost ? ' disabled' : '') + (on ? ' aria-pressed="true"' : ' aria-pressed="false"') + '>' +
                '<span class="ht-swatch" data-swatch="' + s.id + '"></span><span>' + s.name + '</span><small>' + label + '</small></button>';
        }).join('');
        box.innerHTML = '<p class="ht-wallet">You have <strong>' + fmt(state.gears) + '</strong> gears.</p>' +
            '<div class="ht-items">' + cards.join('') + '</div>' +
            '<h3 class="ht-sub-head">Ring skins</h3><div class="ht-skins">' + skins + '</div>';
        box.querySelectorAll('[data-swatch]').forEach(function (sw) {
            var s = SKINS.filter(function (x) { return x.id === sw.getAttribute('data-swatch'); })[0];
            if (s.colors) sw.style.background = 'linear-gradient(135deg, ' + s.colors[1] + ', ' + s.colors[0] + ')';
        });
    }

    function buy(id) {
        if (id === 'saver') {
            if (state.saves >= SAVER.max || state.gears < SAVER.cost) return;
            state.gears -= SAVER.cost;
            state.saves += 1;
        } else {
            var u = UPGRADES.filter(function (x) { return x.id === id; })[0];
            if (!u) return;
            var level = state.up[id];
            if (level >= u.costs.length || state.gears < u.costs[level]) return;
            state.gears -= u.costs[level];
            state.up[id] = level + 1;
            if (id === 'bag' && game.phase !== 'title' && game.phase !== 'over') {
                game.ringsLeft += u.values[level + 1] - u.values[level];
            }
        }
        sfx('buy');
        saveState();
        renderShop();
        hud();
    }

    function chooseSkin(id) {
        var s = SKINS.filter(function (x) { return x.id === id; })[0];
        if (!s) return;
        if (state.skins.indexOf(id) === -1) {
            if (state.gears < s.cost) return;
            state.gears -= s.cost;
            state.skins.push(id);
            sfx('buy');
        }
        state.skin = id;
        saveState();
        renderShop();
        hud();
    }

    function showTab(name) {
        root.querySelectorAll('[data-ht-tab]').forEach(function (tab) {
            var on = tab.getAttribute('data-ht-tab') === name;
            tab.setAttribute('aria-selected', on ? 'true' : 'false');
            tab.tabIndex = on ? 0 : -1;
        });
        root.querySelectorAll('[data-ht-panel]').forEach(function (panel) {
            panel.hidden = panel.getAttribute('data-ht-panel') !== name;
        });
        if (name === 'museum') {
            // Draw first so this visit still shows the "New" pills; the tab badge clears.
            renderMuseum();
            var changed = false;
            state.unlocked.forEach(function (id) {
                if (state.seen.indexOf(id) === -1) { state.seen.push(id); changed = true; }
            });
            if (changed) {
                saveState();
                hud();
            }
        }
    }

    root.addEventListener('click', function (e) {
        var t = e.target.closest('button');
        if (!t || !root.contains(t)) return;
        var action = t.getAttribute('data-ht-action');
        if (action === 'start') startRound();
        else if (action === 'shop') {
            showTab('shop');
            root.querySelector('[data-ht-tab="shop"]').scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
        }
        if (t.hasAttribute('data-ht-buy')) buy(t.getAttribute('data-ht-buy'));
        if (t.hasAttribute('data-ht-skin')) chooseSkin(t.getAttribute('data-ht-skin'));
        if (t.hasAttribute('data-ht-tab')) showTab(t.getAttribute('data-ht-tab'));
        if (t.hasAttribute('data-ht-sound')) {
            state.sound = !state.sound;
            saveState();
            hud();
        }
    });

    root.querySelector('[role="tablist"]').addEventListener('keydown', function (e) {
        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
        var tabs = Array.prototype.slice.call(root.querySelectorAll('[data-ht-tab]'));
        var i = tabs.indexOf(document.activeElement);
        if (i === -1) return;
        var next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
        showTab(next.getAttribute('data-ht-tab'));
        next.focus();
        e.preventDefault();
    });

    // --- Boot ----------------------------------------------------------------------------
    resize();
    setField();
    game.ringsLeft = upgrade('bag');
    showOverlay('title');
    renderMuseum();
    renderShop();
    hud();
    root.classList.add('is-ready');
    window.requestAnimationFrame(frame);
})();
