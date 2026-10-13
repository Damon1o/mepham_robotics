"""New member guide (/guide): a chapter-by-chapter tour of the whole site.

Each chapter says where the feature lives and walks through it in steps; its guided
tour (TOURS, below) shows the same thing on the real pages. Members tick chapters off;
the keys they finish are kept on the account (users.guide_done), so the list here is
also what the save route accepts.

Step text is trusted HTML written here (only <b>, <kbd> and <a>), never user input.
A chapter or step with `when` only shows if that site feature is turned on, and a
chapter with `role` only shows to members with at least that role.
"""

# key, title, icon, blurb, where (menu path), steps; role for editor/admin chapters
CHAPTERS = [
    {
        'key': 'signin',
        'title': 'Sign in and stay safe',
        'icon': 'log-in',
        'blurb': 'Your account opens the members-only side of the site. Keep it yours.',
        'where': ['Menu', 'Member Login'],
        'steps': [
            'Sign in with your <b>username or email</b>. Tick <b>Remember me</b> only on a device that is yours.',
            'Forgot your password? There is no reset email: ask a club admin for a <b>reset link</b>. '
            'It works once and expires after an hour.',
            'Open <b>Account → Two-step sign-in</b> and scan the code with an authenticator app. '
            'Save your <b>backup codes</b> (Copy, Download or Print) somewhere safe.',
            '<b>Where you\'re signed in</b> lists every device on your account. Sign one out, or use '
            '<b>Sign out everywhere</b> if a phone or laptop goes missing.',
            'The <b>Security checkup</b> at the top of Account shows what is still left to do.',
        ],
    },
    {
        'key': 'around',
        'title': 'Find your way around',
        'icon': 'compass',
        'blurb': 'One menu, one search box, and a few shortcuts get you anywhere.',
        'where': ['Top-left', 'MENU'],
        'steps': [
            'Tap <b>MENU</b> to open the sidebar. <b>Explore</b> and <b>Get involved</b> are the public pages; '
            'the <b>Members</b> section only appears while you are signed in.',
            '<b>Teams</b> opens every robot team, newest season first, with groups (like Media) at the bottom.',
            'Press <kbd>Ctrl</kbd> + <kbd>K</kbd> (<kbd>⌘</kbd> + <kbd>K</kbd> on a Mac) on any page to search '
            'pages and teams. Members-only pages show up in search once you are signed in.',
            'Your name at the bottom of the menu opens <b>your member page</b>; <b>Account</b> and '
            '<b>Log out</b> sit right under it.',
            'The footer has the <b>light / dark theme</b> switch, the newsletter sign-up and the safety quiz.',
            ('Stuck? The chat bubble in the bottom-right corner is <b>Steven</b>, the club assistant. '
             'Ask him about meetings, teams or how to join.', 'assistant'),
        ],
    },
    {
        'key': 'account',
        'title': 'Set up your account',
        'icon': 'user-cog',
        'blurb': 'Your name and photo come from here and show up everywhere you appear.',
        'where': ['Menu', 'Account'],
        'steps': [
            'Under <b>Profile</b>, set your <b>full name</b>, email and a <b>photo</b>. They update your '
            'team rosters, your member page and the About page in one go.',
            'Change your password under <b>Password</b>. It needs at least 8 characters.',
            'In <b>Preferences</b>, pick where you land <b>after signing in</b>: Home, the Member Hub, '
            'your team or Events.',
            'Prefer calmer pages? Set <b>Motion</b> to Reduced. <b>Theme</b> picks light, dark or your '
            'device\'s setting. Both are saved on this device only.',
            '<b>My history</b> shows the teams and seasons you have been part of; <b>Recent activity</b> '
            'lists password, two-step and device changes.',
        ],
    },
    {
        'key': 'page',
        'title': 'Build your member page',
        'icon': 'id-card',
        'blurb': 'A portfolio of what you did in the club, ready for college applications.',
        'where': ['Menu', 'Your name', 'My page'],
        'steps': [
            'Your name on any team roster links to this page for other members. Click <b>Edit page</b> to fill it in.',
            'Write a <b>headline</b>, an <b>About me</b> and your <b>Class of</b> year.',
            '<b>Add an entry</b> for awards, roles and outreach. Add the hours and a <b>proof link</b>, and '
            'tick <b>Pin to the top</b> to put your best ones in Highlights.',
            'Drop <b>photos</b> straight onto the page, and <b>Add a link</b> to your CAD, code or videos.',
            ('<b>Who can see this page</b>: Members only, or <b>Anyone with the link</b> for college '
             'applications and résumés. Public pages are never listed in search engines.', 'public_pages'),
            'The <b>College-app kit</b> (only you and admins see it) has a checklist and a Common App '
            'activity you can <b>Copy</b>. Use <b>Print portfolio</b> for a paper or PDF copy.',
        ],
    },
    {
        'key': 'team',
        'title': 'Edit your team page',
        'icon': 'bot',
        'blurb': 'Everyone on a roster can keep their team\'s public page up to date.',
        'where': ['Menu', 'My Team'],
        'steps': [
            '<b>My Team</b> opens the editor for the team you are on. On a team and a group? You get a '
            'short list to pick from. Not on a roster yet? Ask a captain to add you.',
            'Every field <b>saves as you type</b>; watch for <b>All changes saved</b>.',
            'Fill in the team <b>identity</b> (nickname, photo and page layout), <b>Robot specs</b>, and '
            '<b>Season goals</b> with how far along each one is.',
            'In the <b>Roster</b> you can edit <b>your own row</b>: your role, sub-team and the year you joined. '
            'Ask an admin to add or move teammates.',
            'Past seasons keep their own pages. Switch season at the top of the editor to look back.',
        ],
    },
    {
        'key': 'hub',
        'title': 'Use the Member Hub',
        'icon': 'book-open',
        'blurb': 'Your home base: this week at a glance, the club\'s links and build tools.',
        'where': ['Menu', 'Members', 'Member Hub'],
        'steps': [
            '<b>This week</b> shows the next meeting (it says <b>Now</b> while one is running), days to the next '
            'competition and the rosters you are on.',
            'Press <kbd>/</kbd> to search the library, or filter it with the shelf chips.',
            'Tap the <b>star</b> on any link. Stars are saved to your account, so they follow you to every device. '
            'The <b>Starred</b> chip shows only those.',
            'The <b>New</b> chip lists links added since your last visit, and <b>Recently opened</b> brings back '
            'what you used last.',
            'Use the <b>Drivetrain calculator</b> to compare gear ratios, wheel sizes and motor cartridges.',
            'The Hub also links the <b>Glossary</b>, <b>Design Standards</b>, <b>Branding Guide</b> and '
            '<b>Engineering Notebook</b>.',
        ],
    },
    {
        'key': 'events',
        'title': 'Events and RSVPs',
        'icon': 'calendar-days',
        'blurb': 'Competitions, outreach, fundraisers and meetings, all in one calendar.',
        'where': ['Menu', 'Events'],
        'steps': [
            'Browse the <b>month calendar</b> or the upcoming list. Use the chips to show one kind of event.',
            'Open an event and answer <b>Are you coming?</b> Members see who else is going.',
            'Events you are going to show on your member page, and past ones count toward your history.',
            'Hit <b>Subscribe</b> (or <b>Google</b>) once and every new event lands in your own calendar.',
            'The Home page counts down to the next competition and shows <b>live match results</b> on the day.',
        ],
    },
    {
        'key': 'club',
        'title': 'Tour the club pages',
        'icon': 'school',
        'blurb': 'The public pages are what families, sponsors and new students see. Know them well.',
        'where': ['Menu', 'Explore', 'Get involved'],
        'steps': [
            '<b>Home</b>: the countdown, latest news from the club and how to help.',
            '<b>About</b>: our values and the <b>sub-teams</b>, with everyone on each one.',
            '<b>Achievements</b>: every award and result by season. Use <b>Share</b> to send one to family.',
            '<b>Alumni</b>: where past members went. Some are <b>open to questions</b>, so you can ask them '
            'about college and careers.',
            '<b>Donate</b>: fundraisers, what the money is spent on, and sponsorship tiers.',
            '<b>Contact</b>: the message form, where we meet, and answers to common questions.',
        ],
    },
    {
        'key': 'safety',
        'title': 'Workshop safety',
        'icon': 'hard-hat',
        'blurb': 'Do this before you touch a tool in the workshop.',
        'where': ['Footer', 'Safety Quiz'],
        'steps': [
            'Take the <b>Workshop Safety Quiz</b>. You need <b>70%</b> to pass and can retake it as often as you like.',
            'Read the <b>Build Standards</b> and <b>Pre-Match Checklist</b> in Design Standards.',
            'Not sure how to use a tool? Ask a captain or mentor first. Every time.',
        ],
    },
    {
        'key': 'editors',
        'title': 'Editor tools',
        'icon': 'pencil-ruler',
        'role': 'editor',
        'blurb': 'Editors can work on every team and group page, not just their own.',
        'where': ['Menu', 'Team Pages'],
        'steps': [
            '<b>Team Pages</b> replaces My Team in your menu. It lists every team and group by season, '
            'with your own first.',
            'On any page you can add or remove teammates (drop a .csv or .txt of names to add a whole list), '
            'set everyone\'s photos and roles, and edit the team <b>journey</b>.',
            'The editors-only <b>Details</b> section holds the 3D <b>.stl</b> model, the notebook link and '
            '<b>Hide this team</b> from the menu and search.',
            'Ask an admin to start a <b>new season</b> for a team; the old season stays as history.',
        ],
    },
    {
        'key': 'admins',
        'title': 'Run the site',
        'icon': 'shield',
        'role': 'admin',
        'blurb': 'Admins approve members and edit every word on the site.',
        'where': ['Menu', 'Admin Panel'],
        'steps': [
            '<b>Overview</b> shows what needs attention, starting with <b>sign-ups waiting for approval</b>.',
            '<b>People</b>: approve or reject sign-ups, set roles (member, editor, admin), make reset links '
            'and turn off two-step for someone who lost their phone.',
            '<b>Teams</b>, <b>Events</b>, <b>Awards</b> and <b>Sponsors</b> manage what the public pages show.',
            '<b>Messages</b> is the inbox for the contact form, alumni updates and questions.',
            '<b>Site</b> opens the site editor: change any page\'s text and images, preview a draft, and roll back '
            'from history.',
            'Deleting something shows an <b>Undo</b> button for a few seconds instead of asking first.',
        ],
    },
]

KEYS = {c['key'] for c in CHAPTERS}


# --- Guided tour ------------------------------------------------------------------------
# The same chapters shown on the real pages, one spotlighted element per step.
#   page      endpoint the step lives on (the tour goes there first)
#   match     regex for the path when the endpoint redirects (/people/me → /people/<id>)
#   target    CSS selector to spotlight; None shows the step in the middle of the screen
#   optional  skip the step when the element isn't there (a free agent has no team editor)
#   nav       'open' to show the step with the side menu open
#   when      only when that site feature is on (as for chapter steps)

def _step(page, target, title, text, **opts):
    return {'page': page, 'target': target, 'title': title, 'text': text, **opts}


PEOPLE = r'^/people/[^/]+$'
TEAM = r'^/(my-team|manage/team/[^/]+)$'

TOURS = {
    'signin': [
        _step('account', '#checkup', 'Your security checkup',
              'This card shows what is left to make your account safe. Work through it top to bottom.'),
        _step('account', '#password', 'Your password',
              'Change it here. It needs at least 8 characters. Forgot it one day? Ask a club admin for a '
              '<b>reset link</b>; there is no reset email.'),
        _step('account', '#two-step', 'Two-step sign-in',
              'Turn this on and scan the code with an authenticator app. Then save your <b>backup codes</b> '
              'somewhere safe.'),
        _step('account', '#devices', 'Where you\'re signed in',
              'Every device on your account. Sign one out, or <b>Sign out everywhere</b> if a phone goes missing.'),
    ],
    'around': [
        _step('index', '.menu-toggle', 'The menu',
              'Everything on the site starts here. Tap <b>MENU</b> on any page.'),
        _step('index', '#mySidenav .nav-links', 'Every page',
              '<b>Explore</b> and <b>Get involved</b> are the public pages. The <b>Members</b> section only '
              'shows while you are signed in.', nav='open'),
        _step('index', '#mySidenav [aria-controls="teamDropdown"]', 'Teams',
              'Every robot team, newest season first, with groups like Media at the bottom.', nav='open'),
        _step('index', '#mySidenav .nav-footer', 'That\'s you',
              'Your name opens <b>your member page</b>. <b>Account</b> and <b>Log out</b> sit right below it.',
              nav='open'),
        _step('index', None, 'Search anything',
              'Press <kbd>Ctrl</kbd> + <kbd>K</kbd> (<kbd>⌘</kbd> + <kbd>K</kbd> on a Mac) on any page to jump '
              'to a page or a team.'),
        _step('index', '.theme-toggle', 'Light or dark',
              'Switch the colour theme here, at the very bottom of every page.'),
        _step('index', '#chatbot-bubble', 'Ask Steven',
              'Steven is the club assistant. Ask him about meetings, teams or how things work.',
              when='assistant', optional=True),
    ],
    'account': [
        _step('account', '#profile', 'Your name and photo',
              'Set your <b>full name</b>, email and <b>photo</b> here. They update your rosters, member page '
              'and the About page in one go.'),
        _step('account', '#preferences', 'Preferences',
              'Pick where you land <b>after signing in</b>, and set the theme and motion for this device.'),
        _step('account', '#history', 'My history',
              'The teams and seasons you have been part of, kept for you.'),
        _step('account', '#activity', 'Recent activity',
              'Password, two-step and device changes show up here, so you can spot anything odd.'),
    ],
    'page': [
        _step('my_person_page', '[data-edit-toggle]', 'Edit your page',
              'Click <b>Edit page</b> to write a headline, an About me and your Class of year, and to choose '
              '<b>who can see this page</b>.', match=PEOPLE),
        _step('my_person_page', '#honors', 'Awards, roles and outreach',
              '<b>Add an entry</b> with the hours and a <b>proof link</b>. <b>Pin</b> your best ones to show them '
              'in Highlights.', match=PEOPLE, optional=True),
        _step('my_person_page', '#photos', 'Photos',
              'Drop photos straight onto the page while you are editing.', match=PEOPLE, optional=True),
        _step('my_person_page', '[data-copy-link]', 'Share it',
              '<b>Copy link</b> sends your page to anyone allowed to see it. <b>Print portfolio</b> makes a '
              'paper or PDF copy.', match=PEOPLE),
        _step('my_person_page', '#kit', 'College-app kit',
              'Only you and the admins see this: a checklist for your portfolio and a Common App activity '
              'you can <b>Copy</b>.', match=PEOPLE, optional=True),
    ],
    'team': [
        _step('my_team', '.my-team-empty', 'Not on a team yet',
              'Once an admin puts you on a roster, this page becomes your team\'s editor.',
              match=TEAM, optional=True),
        _step('my_team', '.team-picker', 'Pick a page',
              'You are on more than one roster, so pick the page you want to edit.', match=TEAM, optional=True),
        _step('my_team', '#saveStatus', 'It saves as you type',
              'No save button: watch for <b>All changes saved</b> here.', match=TEAM, optional=True),
        _step('my_team', '#s-identity', 'Team identity',
              'Nickname, team photo and the <b>layout</b> the public page uses.', match=TEAM, optional=True),
        _step('my_team', '#s-specs', 'Robot specs',
              'What your robot is built from. It shows on the public team page.', match=TEAM, optional=True),
        _step('my_team', '#s-goals', 'Season goals',
              'Add goals and set how far along each one is.', match=TEAM, optional=True),
        _step('my_team', '#s-roster', 'Your roster row',
              'You can edit <b>your own row</b>: role, sub-team and the year you joined. Ask an admin to add '
              'or move teammates.', match=TEAM, optional=True),
    ],
    'hub': [
        _step('resources', '.hub-guide', 'This guide lives here',
              'Come back to the Member Hub any time to retake the tour or read the written guide.',
              optional=True),
        _step('resources', '.hub-week', 'This week',
              'The next meeting (it says <b>Now</b> while one is on), days to the next competition and your '
              'rosters.', optional=True),
        _step('resources', '.hub-search', 'Search the library',
              'Press <kbd>/</kbd> to jump here and find any link, doc or tool.', optional=True),
        _step('resources', '.hub-chips', 'Starred and New',
              'Tap the <b>star</b> on any link to keep it on your account. <b>New</b> shows links added since '
              'your last visit.', optional=True),
        _step('resources', '#drivetrain', 'Drivetrain calculator',
              'Compare gear ratios, wheel sizes and motor cartridges before you build.', optional=True),
    ],
    'events': [
        _step('events_page', '.ev-card--feed', 'Never miss one',
              '<b>Subscribe</b> once and every new event lands in your own calendar.', optional=True),
        _step('events_page', '.ev-filters', 'Filter by kind',
              'Show only competitions, outreach, fundraisers or meetings.', optional=True),
        _step('events_page', '#calendar', 'The calendar',
              'Open any event to answer <b>Are you coming?</b> Members see who else is going.', optional=True),
    ],
    'club': [
        _step('about', '#subteams', 'About: the sub-teams',
              'Everyone on each sub-team. Families and new students start here.', optional=True),
        _step('achievements', '#awards', 'Achievements',
              'Every award and result by season. <b>Share</b> one with your family.', optional=True),
        _step('alumni', '#ask', 'Alumni',
              'Where past members went. Some are open to questions about college and careers.', optional=True),
        _step('donate', '#fundraisers', 'Donate',
              'Fundraisers, what the money is spent on, and sponsorship tiers.', optional=True),
        _step('contact', '#contact-form', 'Contact',
              'The message form, where we meet, and answers to common questions.', optional=True),
    ],
    'safety': [
        _step('safety_quiz', '#quizContainer', 'Workshop Safety Quiz',
              'Take this before you use any tool. You need <b>70%</b> to pass and can retake it any time.'),
    ],
    'editors': [
        _step('my_team', '.team-picker', 'Team Pages',
              'Every team and group by season, yours first. Open any of them to edit rosters, the journey and '
              'the editors-only <b>Details</b>.', match=TEAM, optional=True),
    ],
    'admins': [
        _step('admin_dashboard', '.admin-tabs', 'The Admin Panel',
              'Overview, People, Teams, Events, Awards, Messages, Sponsors, Site and Activity.'),
        _step('admin_dashboard', '#tab-users', 'People',
              'Approve sign-ups, set roles, make reset links and turn off two-step for someone who lost their '
              'phone.', optional=True),
        _step('admin_dashboard', '#tab-site', 'Site',
              'Edit any page\'s text and images, preview a draft and roll back from history.', optional=True),
    ],
}

assert set(TOURS) == KEYS, 'every chapter needs a tour'
