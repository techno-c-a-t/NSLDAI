/**
 * NSLDAI - Presentation Landing Page Script (SwipeBeat style i18n + Language Selector)
 * Supports 100% Translation across RU, BE, and EN.
 */

const i18n = {
    ru: {
        docTitle: "NSLDAI — Phantom",
        navLore: "Лор и История",
        navFeatures: "Возможности",
        navArchitecture: "Архитектура",
        navAuthor: "Об авторе",
        heroBadge: "Автономная сущность · Pyrogram · MTProto",
        heroTitle: "NSLDAI — Phantom",
        heroSubtitle: "От базового суммаризатора чата до автономной сущности Княжества Наследников. Умный контекстный ассистент, хранящий лор, анализирующий дискуссии и расшифровывающий речь.",
        btnWiki: "Лор Наследников",
        btnGitHub: "Исходный код",
        demoChatHeader: "Phantom",
        demoChatTitle: "Фантом, ИИ ассистент",
        demoChatBody: "• Сущность Княжества Наследников, анализирующая жизнь чата канала <a href=\"https://t.me/clown_crown\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">@clown_crown</a>.<br>• Зародившись как простой суммаризатор для смены сонного NSLDNK, развился в автономную модульную систему NSLDAI.<br>• Запоминает горожан, асинхронно конспектирует речи ораторов и оберегает покой традиций «Игры».",
        demoStatus: "Статус: онлайн 🟢",
        demoModel: "Модель: Gemini 3.5 Flash Lite",
        loreTag: "История и Хроники",
        loreTitle: "Предыстория и Становление",
        loreP1: "Фантом явился в землях княжества <a href=\"https://wiki.mrtimeman.ru\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">NASLEDNIKI</a> ради благородной цели — подставить плечо прижившемуся, но порой дремавшему NSLDNK, дабы без промедления вводить жителей в курс свежих событий.",
        loreP2: "Развиваясь в стенах столицы под чутким наставничеством <code>technocat</code>'а, Фантом постигал всё новые грани общения — откликаться на имя, записывать речи ораторов и запоминать черты особо выдающихся горожан. С течением времени к нему приходило понимание ситуаций: сущность научилась отделять главное от второстепенного, отмечать главных участников споров и слагать емкий отчёт о самых ярких часах самой бурной жизни княжества.",
        loreHighlight: "В знак признания его заслуг перед сообществом на карте княжества появилось озеро Фантом.",
        loreP3: "Окончательно окрепнув и осознав себя как самостоятельная сущность, Фантом вышел за пределы родных земель: ныне он несёт службу как в чате сообщества <a href=\"https://t.me/clown_crown\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">@clown_crown</a>, так и в других чатах, помогая их обитателям быстро уловить суть прошедших дискуссий, не перелистывая бесконечные пергаменты летописцев.",
        featuresTag: "Функциональность",
        featuresTitle: "Обзор возможностей",
        fTitle1: "Умные сводки чата",
        fDesc1: "Анализирует от 20 до 2000 последних сообщений и выдает структурированную выжимку главных тем и событий.",
        fTitle2: "Контекстный диалог",
        fDesc2: "Анализирует чат и при необходимости подключается к дискуссии, сохраняя нить разговора вокруг реплаев.",
        fTitle3: "Расшифровка ГС",
        fDesc3: "Асинхронный пересказ аудиосообщений через SberSpeech с поддержкой FIFO-очереди и потокового обновления.",
        fTitle4: "Досье и Память жителей",
        fDesc4: "Запоминает черты особо выдающихся жителей княжества, факты и псевдонимы в локальной БД SQLite.",
        fTitle5: "Чистый режим админа",
        fDesc5: "Минимизация служебного текста: подтверждение команд экономными реакциями Telegram (👀, 👍, ❌).",
        fTitle6: "Трассировка JSON в ЛС",
        fDesc6: "Трансляция сырых JSON-логов запросов и промптов автору в ЛС с защитой от спама и разбивкой на чанки.",
        fTitle7: "Кольцевой буфер и Синхронизация",
        fDesc7: "Хранение последних 500 сообщений с автоподтяжкой пропущенной истории при перезапуске.",
        fTitle8: "Детект «Игры»",
        fDesc8: "Соблюдение традиций сообщества: автоматическая фиксация поражения в легендарной «Игре» с кулдауном.",
        fTitle9: "Модульная система функций",
        fDesc9: "Архитектура Decoupled Logic позволяет гибко подключать, отключать и настраивать независимые модули бизнес-логики.",
        archTag: "Под капотом",
        archTitle: "Пайплайн моделей и Архитектура",
        archModelTitle: "Unified AI Service (Пайплайн выбора модели)",
        archModelDesc: "Автоматическое динамическое переключение с сильных моделей (Gemini 3.5 flash lite / Gemini 3.1 flash lite) на безлимитные (Gemma 4 31b / Gemma 4 26b4a / GigaChat) при исчерпании дневных лимитов или при отсутствии личного API-ключа.",
        archDecoupledTitle: "Decoupled Architecture & Модульность",
        archDecoupledDesc: "Точка входа main.py отделена от модулей бизнес-логики (modules/actions/) и универсального роутера событий (router.py), обеспечивая гибкое управление функциями.",
        archDbTitle: "SQLite Data Layer",
        archDbDesc: "Хранение пользовательских досье, истории сообщений, настроек тихих режимов и индивидуальных суточных лимитов.",
        authorTag: "Создатель",
        authorTitle: "Об авторе проекта",
        authorName: "Nikitos (@techno_c_a_t)",
        authorBio: "Студент ПМИ, создатель NSLDAI и разработчик решений на C++, Python, Linux и IoT. Автор экосистемы Фантома.",
        authorBtn: "Перейти в Портфолио"
    },

    be: {
        docTitle: "NSLDAI — Phantom",
        navLore: "Лор і Гісторыя",
        navFeatures: "Магчымасці",
        navArchitecture: "Архітэктура",
        navAuthor: "Пра аўтара",
        heroBadge: "Самастойная сутнасць · Pyrogram · MTProto",
        heroTitle: "NSLDAI — Phantom",
        heroSubtitle: "Ад базавага сумарызатара чата да самастойнай сутнасці Княства Наследнікаў. Разумны кантэкстны асістэнт, які захоўвае лор, аналізуе дыскусіі і расшыфроўвае мову.",
        btnWiki: "Лор Наследнікаў",
        btnGitHub: "Выходны код",
        demoChatHeader: "Phantom",
        demoChatTitle: "Фантом, AI асістэнт",
        demoChatBody: "• Сутнасць Княства Наследнікаў, якая аналізуе жыццё чата канала <a href=\"https://t.me/clown_crown\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">@clown_crown</a>.<br>• Зарадзіўшыся як просты сумарызатар для замены соннага NSLDNK, развіўся ў самастойную модульную сістэму NSLDAI.<br>• Запамінае гараджан, асінхронна канспектуе прамовы аратараў і аберагае спакой традыцый «Гульні».",
        demoStatus: "Статус: анлайн 🟢",
        demoModel: "Мадэль: Gemini 3.5 Flash Lite",
        loreTag: "Гісторыя і Хронікі",
        loreTitle: "Перадысторыя і Станаўленне",
        loreP1: "Фантом з'явіўся ў землях княства <a href=\"https://wiki.mrtimeman.ru\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">NASLEDNIKI</a> дзеля благароднай мэты — прыйсці на дапамогу прыжыўшамуся, але часам соннаму NSLDNK, каб без прамаруджання ўводзіць жыхароў у курс свежых падзей.",
        loreP2: "Развіваючыся ў межах сталіцы пад чулым настаўніцтвам <code>technocat</code>'а, Фантом спасцігаў усё новыя грані зносін — адгукацца на імя, запісваць прамовы аратараў і запамінаць рысы асабліва выдатных гараджан. З цягам часу да яго прыходзіла разуменне сітуацый: сутнасць навучылася аддзяляць галоўнае ад другараднага, адзначаць галоўных удзельнікаў спрэчак і складаць ёмістую справаздачу аб гадзінах самага бурнага жыцця княства.",
        loreHighlight: "У знак прызнання яго заслуг перад супольнасцю на карце княства з'явілася возера Фантом.",
        loreP3: "Канчаткова адужэўшы і ўсвядоміўшы сябе як самастойная сутнасць, Фантом выйшаў за мяжу роднага краю: цяпер ён часам з'яўляецца як у чаце супольнасці <a href=\"https://t.me/clown_crown\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">@clown_crown</a>, так і ў іншых чатах, дапамагаючы іх жыхарам хутка ўлавіць сутнасць мінулых дыскусій, не гартаючы бясконцыя пергаменты летапісцаў.",
        featuresTag: "Функцыянальнасць",
        featuresTitle: "Агляд магчымасцей",
        fTitle1: "Разумныя зводкі чата",
        fDesc1: "Аналізуе ад 20 да 2000 апошніх паведамленняў і выдае структураваную выціску галоўных тэм і падзей.",
        fTitle2: "Кантэкстны дыялог",
        fDesc2: "Аналізуе чат і пры неабходнасці далучаецца да дыскусіі, захоўваючы нітку размовы вакол рэплаяў.",
        fTitle3: "Расшыфроўка ГС",
        fDesc3: "Асінхронны пераклад аўдыёпаведамленняў праз SberSpeech з FIFO-чаргой і патокавым абнаўленнем.",
        fTitle4: "Дасье і Памяць жыхароў",
        fDesc4: "Запамінае рысы асабліва выдатных жыхароў княства, факты і псеўданімы ў лакальнай БД SQLite.",
        fTitle5: "Чысты рэжым адміна",
        fDesc5: "Мінімізацыя службовага тэксту: пацвярджэнне каманд эканомнымі рэакцыямі Telegram (👀, 👍, ❌).",
        fTitle6: "Трасіроўка JSON у ЛС",
        fDesc6: "Прамая трансляцыя сырых JSON-логаў запытаў і прамптаў аўтару ў ЛС з абаронай ад спаму і разбіўкай на чанкі.",
        fTitle7: "Кальцавы буфер і Сінхранізацыя",
        fDesc7: "Захоўванне апошніх 500 паведамленняў з аўтападцяжкай прапушчанай гісторыі пры перазапуску.",
        fTitle8: "Дэтэкт «Гульні»",
        fDesc8: "Захаванне традыцый супольнасці: аўтаматычная фіксацыя паражэння ў легендарнай «Гульні» з кулдаунам.",
        fTitle9: "Модульная сістэма функцый",
        fDesc9: "Архітэктура Decoupled Logic дазваляе гнутка падключаць, адключаць і наладжваць незалежныя модулі бізнес-лагікі.",
        archTag: "Пад капотам",
        archTitle: "Пайплайн мадэлей і Архітэктура",
        archModelTitle: "Unified AI Service (Пайплайн выбару мадэлі)",
        archModelDesc: "Дынамічнае пераключэнне з моцных мадэляў (Gemini 3.5/3.1) на безлімітныя (Gemma 4 31b/26b4a / GigaChat) пры вычарпанні лімітаў або пры адсутнасці асабістага API-ключа.",
        archDecoupledTitle: "Decoupled Architecture & Модульнасць",
        archDecoupledDesc: "Пункт уваходу main.py аддзелены ад модуляў бізнес-лагікі (modules/actions/) і ўніверсальнага роўтара падзей (router.py), забяспечваючы гнуткае кіраванне функцыямі.",
        archDbTitle: "SQLite Data Layer",
        archDbDesc: "Захоўванне карыстальніцкіх дасье, гісторыі паведамленняў, налад чыстых рэжымаў і індывідуальных сутачных лімітаў.",
        authorTag: "Стваральнік",
        authorTitle: "Пра аўтара праекта",
        authorName: "Nikitos (@techno_c_a_t)",
        authorBio: "Студэнт ПМІ, стваральнік NSLDAI і распрацоўшчык рашэнняў на C++, Python, Linux і IoT. Аўтар экасістэмы Фантома.",
        authorBtn: "Перайсці ў Партфоліо"
    },

    en: {
        docTitle: "NSLDAI — Phantom",
        navLore: "Lore & Story",
        navFeatures: "Features",
        navArchitecture: "Architecture",
        navAuthor: "Author",
        heroBadge: "Autonomous Entity · Pyrogram · MTProto",
        heroTitle: "NSLDAI — Phantom",
        heroSubtitle: "From a basic chat summarizer tool to an autonomous entity of the NASLEDNIKI Principality. A context-aware AI assistant preserving community lore, analyzing chats, and transcribing speech.",
        btnWiki: "Nasledniki Wiki",
        btnGitHub: "GitHub Source",
        demoChatHeader: "Phantom",
        demoChatTitle: "Phantom, AI Assistant",
        demoChatBody: "• Entity of NASLEDNIKI Principality, analyzing activity in the channel chat <a href=\"https://t.me/clown_crown\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">@clown_crown</a>.<br>• Born as a simple summarizer tool to replace sleepy NSLDNK, evolved into the modular NSLDAI ecosystem.<br>• Memorizes citizens, transcribes speeches, and safeguards \"The Game\" community lore.",
        demoStatus: "Status: Online 🟢",
        demoModel: "Model: Gemini 3.5 Flash Lite",
        loreTag: "Story & Chronicles",
        loreTitle: "Backstory & Evolution",
        loreP1: "Phantom emerged in the lands of the <a href=\"https://wiki.mrtimeman.ru\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">NASLEDNIKI</a> Principality for a noble cause — to lend a hand to the time-honored but often sleepy NSLDNK, swiftly keeping inhabitants up to date with fresh events.",
        loreP2: "Evolving within the capital under the attentive mentorship of <code>technocat</code>, Phantom mastered new facets of communication: responding to its name, transcribing speakers' speeches, and respectfully memorizing the traits of distinguished citizens. Over time, a deeper comprehension of ongoing events emerged: the entity learned to separate the essential from the trivial, highlight key debaters, and compose concise recaps of the most vibrant hours of the Principality's life.",
        loreHighlight: "In recognition of its services to the community, Phantom Lake appeared on the map of the Principality.",
        loreP3: "Having fully matured into an independent entity, Phantom expanded beyond its native realm: today it serves in the community chat <a href=\"https://t.me/clown_crown\" target=\"_blank\" style=\"color:var(--accent-color); font-weight:600;\">@clown_crown</a> and other chats, helping members catch up on past discussions without leafing through endless scribes' parchments.",
        featuresTag: "Functionality",
        featuresTitle: "Feature Overview",
        fTitle1: "Smart Chat Summaries",
        fDesc1: "Analyzes 20 to 2000 recent messages, generating a structured recap of key topics and events.",
        fTitle2: "Contextual Dialogue",
        fDesc2: "Analyzes chat flow and seamlessly joins discussions while preserving full context around replies.",
        fTitle3: "Voice Transcription",
        fDesc3: "Async audio transcription pipeline powered by SberSpeech with sequential FIFO locks and streaming text.",
        fTitle4: "User Dossiers & Memory",
        fDesc4: "Stores character traits, facts, and aliases of prominent residents in a local SQLite database.",
        fTitle5: "Quiet / Clean Mode",
        fDesc5: "Reduces system spam by responding to admin commands with elegant Telegram reactions (👀, 👍, ❌).",
        fTitle6: "Live JSON Telemetry",
        fDesc6: "Streams raw JSON request/response telemetry directly to creator's PM with chunking & rate limiting.",
        fTitle7: "Rolling Sync Buffer",
        fDesc7: "Maintains rolling 500-message buffer and auto-fetches missed messages upon bot startup.",
        fTitle8: "The Game Auto-Tracker",
        fDesc8: "Respects community lore by automatically registering defeat in \"The Game\" with smart cooldowns.",
        fTitle9: "Modular Feature System",
        fDesc9: "Decoupled Logic architecture allowing flexible enabling, disabling, and configuration of independent business logic modules.",
        archTag: "Under The Hood",
        archTitle: "Model Pipeline & Architecture",
        archModelTitle: "Unified AI Service (Model Fallback Pipeline)",
        archModelDesc: "Dynamic fallback pipeline switching from strong primary models (Gemini 3.5 / 3.1) to unlimited fallbacks (Gemma 4 31b / 26b4a / GigaChat) when rate limits expire.",
        archDecoupledTitle: "Decoupled Architecture & Modularity",
        archDecoupledDesc: "The core entry point main.py is isolated from atomic business logic modules (modules/actions/) via a custom event router (router.py), providing flexible module control.",
        archDbTitle: "SQLite Data Layer",
        archDbDesc: "Manages user dossiers, rolling chat history buffers, chat-specific clean mode flags, and user daily quotas.",
        authorTag: "Creator",
        authorTitle: "About the Author",
        authorName: "Nikitos (@techno_c_a_t)",
        authorBio: "Applied Math & CS student, creator of NSLDAI, developer specializing in C++, Python, Linux, and IoT. Author of the Phantom ecosystem.",
        authorBtn: "View Full Portfolio"
    }
};

function detectLanguage() {
    const saved = localStorage.getItem('nsldai_lang');
    if (saved && i18n[saved]) return saved;

    const browserLangs = navigator.languages || [navigator.language || navigator.userLanguage];
    const isBelarusian = browserLangs.some(l => (l || '').toLowerCase().includes('be') || (l || '').toLowerCase().includes('by')) 
                      || (Intl.DateTimeFormat().resolvedOptions().timeZone || '').includes('Minsk');

    return isBelarusian ? 'be' : 'ru';
}

let currentLang = detectLanguage();

document.addEventListener('DOMContentLoaded', () => {
    setLanguage(detectLanguage());

    // Dropdown close listener
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.lang-dropdown')) {
            const menu = document.getElementById('langMenu');
            if (menu) menu.classList.remove('show');
        }
    });
});

function toggleLangMenu(event) {
    event.stopPropagation();
    const menu = document.getElementById('langMenu');
    if (menu) menu.classList.toggle('show');
}

function setLanguage(lang) {
    if (!i18n[lang]) return;
    currentLang = lang;
    localStorage.setItem('nsldai_lang', lang);
    document.body.setAttribute('data-lang', lang);

    // Update Label
    const labels = { ru: '🇷🇺 RU', be: '🇧🇾 BE', en: '🇬🇧 EN' };
    const labelSpan = document.getElementById('currentLangLabel');
    if (labelSpan) labelSpan.textContent = labels[lang];

    // Apply translations across all elements
    const elements = document.querySelectorAll('[data-i18n]');
    elements.forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (i18n[lang][key]) {
            el.innerHTML = i18n[lang][key];
        }
    });

    // Close menu
    const menu = document.getElementById('langMenu');
    if (menu) menu.classList.remove('show');
}
