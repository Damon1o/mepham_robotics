"""New member guide (/guide): a chapter-by-chapter tour of the whole site.

Each chapter says where the feature lives, walks through it in steps, and links to
the real page to try it. Members tick chapters off; the keys they finish are kept on
the account (users.guide_done), so the list here is also what the save route accepts.

Step text is trusted HTML written here (only <b>, <kbd> and <a>), never user input.
A chapter or step with `when` only shows if that site feature is turned on, and a
chapter with `role` only shows to members with at least that role.
"""

# key, title, icon, blurb, where (menu path), steps, try link (label, endpoint, anchor), extras
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
        'try': ('Open security settings', 'account', 'two-step'),
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
        'try': ('Open search', 'index', None),
        'search': True,
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
        'try': ('Open Account', 'account', 'profile'),
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
        'try': ('Open my page', 'my_person_page', None),
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
        'try': ('Open My Team', 'my_team', None),
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
        'try': ('Open the Hub', 'resources', None),
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
        'try': ('Open Events', 'events_page', None),
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
        'try': ('Open About', 'about', None),
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
        'try': ('Take the quiz', 'safety_quiz', None),
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
        'try': ('Open Team Pages', 'my_team', None),
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
        'try': ('Open Admin Panel', 'admin_dashboard', None),
    },
]

KEYS = {c['key'] for c in CHAPTERS}
