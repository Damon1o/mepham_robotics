"""Admin-editable site copy and settings.

Every field has a default equal to what the templates showed before this
existed, so an empty database renders the site unchanged. Only overrides are
stored, in one document: site_metadata {_id: 'site_content', values: {section: {field: value}}}.
Resetting a field removes its override.

This module is pure: no Flask app, no database. api/index.py wires the
routes, the storage, and the `site` template global.
"""
import datetime
import os
import re

from markupsafe import Markup, escape

DAY_NAMES = ('Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday')

# Lucide icon names offered for cards. Kept short so the picker stays usable;
# every name here exists in the lucide release base.html loads.
ICONS = ('target', 'lightbulb', 'handshake', 'mountain', 'scale', 'graduation-cap', 'cog', 'zap', 'code',
         'notebook-pen', 'globe', 'hard-hat', 'trophy', 'rocket', 'wrench', 'cpu', 'users', 'heart',
         'star', 'shield', 'flag', 'book-open', 'award', 'medal', 'calendar', 'map-pin', 'sparkles',
         'hammer', 'bot', 'brain', 'compass', 'flame', 'leaf', 'megaphone', 'microscope', 'puzzle',
         'ruler', 'smile', 'sun', 'timer')

SOCIAL_PLATFORMS = {
    # platform: (label, lucide icon, allowed hosts)
    'instagram': ('Instagram', 'instagram', ('instagram.com',)),
    'facebook': ('Facebook', 'facebook', ('facebook.com', 'fb.com')),
    'x': ('X', 'twitter', ('x.com', 'twitter.com')),
    'youtube': ('YouTube', 'youtube', ('youtube.com', 'youtu.be')),
    'tiktok': ('TikTok', 'music-2', ('tiktok.com',)),
    'discord': ('Discord', 'message-circle', ('discord.gg', 'discord.com')),
    'github': ('GitHub', 'github', ('github.com',)),
    'linkedin': ('LinkedIn', 'linkedin', ('linkedin.com',)),
    'threads': ('Threads', 'at-sign', ('threads.net', 'threads.com')),
}

TIER_COLOURS = ('bronze', 'silver', 'gold', 'platinum')
TONES = ('info', 'celebrate', 'alert')
COUNTDOWN_MODES = ('always', 'scheduled', 'never')
# Team page layouts: key -> name shown in the pickers. Each key has a template at
# templates/team_layouts/<key>.html; any key but 'classic' also loads
# static/css/pages/team-layouts/<key>.css.
TEAM_LAYOUTS = {
    'classic': 'Classic Stack',
    'scoreboard': 'Scoreboard',
    'spotlight': 'Robot Spotlight',
    'meet': 'Meet the Team',
    'dossier': 'Dossier',
    'tabs': 'Tabbed Hub',
    'timeline': 'Season Timeline',
    'magazine': 'Magazine',
    'bento': 'Bento Dashboard',
    'compact': 'Compact Card',
}
DEFAULT_TEAM_LAYOUT = 'classic'
# The Competition Awards design each layout shows: templates/partials/awards/<style>.html,
# plus static/css/pages/awards/<style>.css for any style but 'classic'. Layouts not
# listed keep the classic tile grid.
LAYOUT_AWARD_STYLES = {
    'meet': 'mosaic',
    'tabs': 'mosaic',
    'bento': 'mosaic',
    'dossier': 'plaque',
    'compact': 'plaque',
    'spotlight': 'shelf',
    'magazine': 'shelf',
    'scoreboard': 'banners',
    'timeline': 'banners',
}
FUNDRAISERS_MAX = 20
MONEY_MAX = 1_000_000


class Field:
    """One editable value.

    kind: text | textarea | rich | url | link | email | toggle | choice | time | days |
          number | datetime | image | list
    rich text allows **bold**, [label](link) and blank-line paragraphs; nothing else.
    `items` describes a list row as a tuple of Fields (kind list only).
    Text may use placeholders like {room} or {tagline}; see TOKENS.
    """

    def __init__(self, key, kind, label, default, *, max=None, required=False, hint='', choices=None,
                 items=None, max_items=None, min_value=None, max_value=None, group=None, pattern=None,
                 hint_link=None):
        self.key, self.kind, self.label, self.default = key, kind, label, default
        self.max, self.required, self.hint, self.pattern = max, required, hint, pattern
        # (label, dashboard tab): a link to where the hint says the thing really lives.
        self.hint_link = hint_link
        self.choices, self.items, self.max_items = choices, items, max_items
        self.min_value, self.max_value, self.group = min_value, max_value, group


class Section:
    def __init__(self, key, title, icon, fields, *, role='admin', page=None, blurb=''):
        self.key, self.title, self.icon, self.fields = key, title, icon, fields
        self.role, self.page, self.blurb = role, page, blurb
        self.by_key = {f.key: f for f in fields}


def _card(icon, title, text, link_label='', link_url=''):
    return {'icon': icon, 'title': title, 'text': text, 'link_label': link_label, 'link_url': link_url}


CARD_ITEMS = (
    Field('icon', 'choice', 'Icon', 'star', choices=ICONS),
    Field('title', 'text', 'Title', '', max=40, required=True),
    Field('text', 'textarea', 'Text', '', max=400),
)
CARD_WITH_LINK_ITEMS = CARD_ITEMS + (
    Field('link_label', 'text', 'Button label', '', max=30),
    Field('link_url', 'link', 'Button link', '', max=300),
)

SECTIONS = (
    Section('announcement', 'Announcement bar', 'megaphone', (
        Field('enabled', 'toggle', 'Show the announcement', False,
              hint='A strip across the top of every page. Use it for tryouts, event days or closures.'),
        Field('text', 'rich', 'Message', '', max=240, hint='One or two sentences.'),
        Field('tone', 'choice', 'Style', 'info', choices=TONES),
        Field('link_label', 'text', 'Button label', '', max=30, hint='Optional button at the end, like "Sign up".'),
        Field('link_url', 'link', 'Button link', '', max=300),
        Field('starts', 'datetime', 'Show from', '', hint='Optional. Club time zone.'),
        Field('ends', 'datetime', 'Hide after', '', hint='Optional. It hides itself after this time.'),
        Field('dismissible', 'toggle', 'Visitors can close it', True),
    ), blurb='Site-wide notice'),

    Section('general', 'Club details', 'flag', (
        Field('club_name', 'text', 'Club name', 'Mepham Robotics Club', max=60, required=True,
              hint='Used in link previews, the footer and page titles.'),
        Field('short_name', 'text', 'Short name', 'Mepham Robotics', max=40, required=True),
        Field('tagline', 'text', 'Tagline', 'Build. Code. Compete.', max=60, required=True),
        Field('contact_email', 'email', 'Club email', 'damlin@bmchsd.com', max=254, required=True,
              hint='Shown on the contact page and used for replies about donations.'),
        Field('meta_description', 'textarea', 'Default search description',
              'Mepham Robotics Club (Team 77628) — Building robots, coding futures, and competing in VEX Robotics.',
              max=200, hint='What Google shows under the site name. About 150 characters.'),
    ), blurb='Name, tagline, email'),

    Section('social', 'Social links', 'at-sign', (
        Field('links', 'list', 'Accounts', [{'platform': 'instagram', 'url': 'https://instagram.com/mephamrobotics'}],
              items=(Field('platform', 'choice', 'Platform', 'instagram', choices=tuple(SOCIAL_PLATFORMS)),
                     Field('url', 'url', 'Profile link', '', max=300, required=True)),
              max_items=8, hint='Shown in the footer and on the contact page.'),
    ), blurb='Footer and contact icons'),

    Section('meeting', 'Meetings & location', 'map-pin', (
        Field('days', 'days', 'Meeting days', [2, 5]),
        Field('start', 'time', 'Starts', '15:00'),
        Field('end', 'time', 'Ends', '17:00'),
        Field('room', 'text', 'Room', 'Room LL01', max=60),
        Field('school', 'text', 'School', 'Wellington C. Mepham High School', max=100),
        Field('school_short', 'text', 'School (short)', 'Wellington C. Mepham HS', max=60),
        Field('map_query', 'text', 'Map search', 'Wellington C. Mepham High School', max=150,
              hint='What Google Maps searches for on the contact page.'),
    ), blurb='When and where the club meets'),

    Section('home', 'Homepage', 'house', (
        Field('hero_title', 'text', 'Big title', 'Mepham Robotics', max=40, required=True, group='Top of the page'),
        Field('hero_tagline', 'text', 'Tagline', '{tagline}', max=80, group='Top of the page',
              hint='{tagline} uses the club tagline from Club details.'),
        Field('hero_image', 'image', 'Background photo', None, group='Top of the page',
              hint='Wide photos work best. Leave empty for the standard photo.'),
        Field('cta_primary_label', 'text', 'First button', 'Learn More', max=24, group='Top of the page'),
        Field('cta_primary_url', 'link', 'First button link', '/about', max=300, group='Top of the page'),
        Field('cta_secondary_label', 'text', 'Second button', 'Support Us', max=24, group='Top of the page'),
        Field('cta_secondary_url', 'link', 'Second button link', '/donate', max=300, group='Top of the page'),
        Field('countdown_mode', 'choice', 'Countdown', 'always', choices=COUNTDOWN_MODES, group='Countdown & events',
              hint='"Scheduled" hides the countdown when no event is coming up.'),
        Field('countdown_heading', 'text', 'Countdown heading', 'Next Competition In:', max=60,
              group='Countdown & events'),
        Field('events_heading', 'text', 'Events heading', 'Upcoming Events', max=60, group='Countdown & events'),
        Field('events_empty', 'text', 'When there are no events',
              'No upcoming events scheduled at this time. Check back soon!', max=160, group='Countdown & events'),
        Field('show_stats', 'toggle', 'Show the club numbers', True, group='Sections',
              hint='The numbers themselves are set on the dashboard.', hint_link=('Overview', 'overview')),
        Field('show_gallery', 'toggle', 'Show the photo gallery', True, group='Sections'),
        Field('gallery_heading', 'text', 'Gallery heading', 'Team Gallery', max=60, group='Sections'),
        Field('show_donate', 'toggle', 'Show the donation band', True, group='Sections'),
        Field('donate_heading', 'text', 'Donation heading', 'Want to Support Us?', max=60, group='Sections'),
        Field('donate_body', 'textarea', 'Donation text',
              'Your donation helps us compete at the highest level, acquire new parts, and continue building '
              'innovative robots.', max=300, group='Sections'),
        Field('donate_button', 'text', 'Donation button', 'Donate Now', max=24, group='Sections'),
        Field('meta_description', 'textarea', 'Search description',
              'Mepham Robotics Club (Team 77628) — Building robots, coding futures, and competing in VEX Robotics. '
              'Join the legacy.', max=200, group='Search & sharing'),
    ), page='index', blurb='Hero, countdown, sections'),

    Section('fundraisers', 'Fundraisers', 'piggy-bank', (
        Field('mode', 'choice', 'Homepage section', 'scheduled', choices=COUNTDOWN_MODES, group='Homepage section',
              hint='"Scheduled" hides the section when no fundraiser is coming up.'),
        Field('heading', 'text', 'Heading', 'Next Fundraiser', max=60, required=True, group='Homepage section'),
        Field('more_heading', 'text', 'Heading for the rest', 'More Ways to Help', max=60, group='Homepage section'),
        Field('empty_text', 'text', 'When there are no fundraisers',
              'No fundraisers right now. Check back soon!', max=160, group='Homepage section'),
        Field('show_progress', 'toggle', 'Show progress bars', True, group='Homepage section',
              hint='Only for fundraisers with a goal.'),
        Field('max_shown', 'number', 'How many to show', 4, min_value=1, max_value=FUNDRAISERS_MAX,
              group='Homepage section', hint='The next one is shown big; the rest sit below it.'),
        Field('entries', 'list', 'Fundraisers', [], items=(
            Field('name', 'text', 'Name', '', max=80, required=True),
            Field('starts', 'datetime', 'Starts', '', required=True),
            Field('ends', 'datetime', 'Ends', '', hint='Optional'),
            Field('location', 'text', 'Where', '', max=100),
            Field('description', 'textarea', 'Description', '', max=400),
            Field('image', 'image', 'Photo', None),
            Field('link_label', 'text', 'Button label', '', max=30),
            Field('link_url', 'link', 'Button link', '', max=300),
            Field('goal', 'number', 'Goal ($)', None, min_value=0, max_value=MONEY_MAX),
            Field('raised', 'number', 'Raised so far ($)', None, min_value=0, max_value=MONEY_MAX),
            Field('featured', 'toggle', 'Pin as next', False),
            Field('hidden', 'toggle', 'Draft (hidden)', False),
        ), max_items=FUNDRAISERS_MAX, group='Fundraisers',
            hint='Past fundraisers drop off the homepage on their own.'),
        Field('owner_group', 'text', 'Fundraising group', 'fundraising', max=40, pattern=r'[a-z0-9]+(?:-[a-z0-9]+)*',
              group='Who can edit', hint='Everyone on this group can edit this page. Editors and admins always can.'),
    ), role='fundraisers', page='index', blurb='Homepage fundraisers'),

    Section('gallery', 'Photo gallery', 'images', (
        Field('photos', 'list', 'Photos', [{'image': {'key': f'photos/carousel{n}'}, 'alt': f'Team photo {n}'}
                                           for n in range(1, 11)],
              items=(Field('image', 'image', 'Photo', None, required=True),
                     Field('alt', 'text', 'Description', '', max=150, required=True,
                           hint='What the photo shows, for screen readers.')),
              max_items=24, hint='Scrolls on the homepage and the About page. Change the order with the arrows.'),
    ), page='index', blurb='Homepage and About carousel'),

    Section('about', 'About page', 'info', (
        Field('hero_title', 'text', 'Big title', 'About Us', max=40, required=True, group='Top of the page'),
        Field('hero_tagline', 'text', 'Tagline', 'Innovation Driven by Passion', max=80, group='Top of the page'),
        Field('hero_image', 'image', 'Background photo', None, group='Top of the page'),
        Field('who_heading', 'text', 'Heading', 'Who We Are', max=60, group='Who we are'),
        Field('who_body', 'rich', 'Text',
              'We are a **student-led robotics club** competing in the **VEX V5 Robotics Competition**. Our '
              'members learn hands-on mechanical design, electrical engineering, and complex C++ / Python '
              'programming.\n\nThrough intense competition and collaboration, we push the boundaries of what '
              'high school students can achieve in robotics and engineering.\n\nOur teams work year-round to '
              'design, build, and program competitive robots that can tackle the season\'s challenges with '
              'precision and creativity.', max=2000, group='Who we are'),
        Field('values_heading', 'text', 'Heading', 'What We Stand For', max=60, group='Values'),
        Field('values', 'list', 'Value cards', [
            _card('target', 'Excellence', 'We strive for excellence in every aspect of robotics - from mechanical '
                  'design to autonomous programming.'),
            _card('lightbulb', 'Innovation', 'We encourage creative thinking and innovative solutions to complex '
                  'engineering challenges.'),
            _card('handshake', 'Collaboration', 'Teamwork is at our core. The best solutions come from diverse '
                  'minds working together, and we carry that spirit into our school and local community by '
                  'giving back.'),
            _card('mountain', 'Perseverance', 'We embrace challenges and learn from failures, constantly improving '
                  'our robots and ourselves.'),
            _card('scale', 'Integrity', 'We compete with honesty and fairness, upholding the highest standards of '
                  'sportsmanship.'),
            _card('graduation-cap', 'Mentorship', 'Experienced members guide new team members, fostering a culture '
                  'of continuous learning.'),
        ], items=CARD_ITEMS, max_items=9, group='Values'),
        Field('subteams_heading', 'text', 'Heading', 'Our Sub-Teams', max=60, group='Sub-teams'),
        Field('subteams', 'list', 'Sub-team cards', [
            _card('cog', 'Mechanical', 'CAD, fabrication, drivetrain and manipulator design.'),
            _card('zap', 'Electrical', 'Wiring, sensors, and V5 brain configuration.'),
            _card('code', 'Programming', 'C++ and Python, autonomous routines, odometry.'),
            _card('notebook-pen', 'Notebook & Outreach', 'Engineering notebook, judging interviews, community '
                  'events.'),
        ], items=CARD_ITEMS, max_items=8, group='Sub-teams'),
        Field('culture_heading', 'text', 'Heading', 'Culture & Safety', max=60, group='Culture'),
        Field('culture', 'list', 'Culture cards', [
            _card('globe', 'Diversity & Inclusion', 'Mepham Robotics is committed to fostering an inclusive '
                  'environment where students of all backgrounds can thrive in STEM. We believe that diverse '
                  'perspectives lead to better engineering solutions and a stronger community.'),
            _card('hard-hat', 'Team Safety Captain', 'Our dedicated Safety Captain ensures all team members adhere '
                  'to safety protocols, manages the safety manual, and conducts regular workshop inspections.',
                  'Take Safety Quiz', '/safety-quiz'),
        ], items=CARD_WITH_LINK_ITEMS, max_items=4, group='Culture'),
        Field('gallery_heading', 'text', 'Gallery heading', 'Team Moments', max=60, group='Culture'),
        Field('meta_description', 'textarea', 'Search description',
              'Learn about the Mepham Robotics Club mission, our sub-teams, and our history of excellence in VEX '
              'Robotics.', max=200, group='Search & sharing'),
    ), page='about', blurb='Story, values, sub-teams'),

    Section('donate', 'Donate page', 'heart-handshake', (
        Field('hero_title', 'text', 'Big title', 'Support Us', max=40, required=True, group='Top of the page'),
        Field('hero_tagline', 'text', 'Tagline', 'Help Build The Future', max=80, group='Top of the page'),
        Field('hero_image', 'image', 'Background photo', None, group='Top of the page'),
        Field('givebutter_id', 'text', 'Givebutter campaign ID', os.getenv('GIVEBUTTER_CAMPAIGN_ID', ''), max=40,
              group='Online donations', pattern=r'[A-Za-z0-9_-]+',
              hint='The code at the end of your Givebutter campaign link. Leave empty to show the email fallback.'),
        Field('intro_heading', 'text', 'Heading', 'Support Our Mission', max=60, group='Online donations'),
        Field('intro_subheading', 'text', 'Subheading', 'Every Donation Makes a Difference', max=80,
              group='Online donations'),
        Field('intro_body', 'textarea', 'Text',
              'Your generous donation helps us compete at the highest level, purchase new parts and equipment, '
              'travel to competitions, and continue building innovative robots that push the boundaries of '
              'what\'s possible.', max=600, group='Online donations'),
        Field('note', 'textarea', 'Small print',
              'Mepham Robotics Club is a registered student organization. All donations go directly to '
              'supporting our teams.', max=300, group='Online donations'),
        Field('tiers_heading', 'text', 'Heading', 'Sponsorship Levels', max=60, group='Sponsorship levels'),
        Field('tiers', 'list', 'Levels', [
            {'name': 'Bronze Sponsor', 'amount': '$50+', 'colour': 'bronze',
             'benefits': 'Name on website\nThank you email\nTeam updates newsletter'},
            {'name': 'Silver Sponsor', 'amount': '$150+', 'colour': 'silver',
             'benefits': 'All Bronze benefits\nLogo on team shirts\nSocial media shoutout\nInvite to competitions'},
            {'name': 'Gold Sponsor', 'amount': '$500+', 'colour': 'gold',
             'benefits': 'All Silver benefits\nLogo on robot\nFeatured sponsor banner\nTeam presentation'},
        ], items=(Field('name', 'text', 'Name', '', max=40, required=True),
                  Field('amount', 'text', 'Amount', '', max=20),
                  Field('colour', 'choice', 'Colour', 'bronze', choices=TIER_COLOURS),
                  Field('benefits', 'textarea', 'Benefits (one per line)', '', max=600)),
              max_items=5, group='Sponsorship levels'),
        Field('show_impact', 'toggle', 'Show "Your Impact"', True, group='Your impact'),
        Field('impact_heading', 'text', 'Heading', 'Your Impact', max=60, group='Your impact'),
        Field('impact', 'list', 'Impact cards', [
            {'amount': '$25', 'text': 'Buys a VEX motor'},
            {'amount': '$50', 'text': 'Funds team transportation'},
            {'amount': '$100', 'text': 'Covers competition registration'},
            {'amount': '$250', 'text': 'Supplies essential build materials'},
        ], items=(Field('amount', 'text', 'Amount', '', max=12, required=True),
                  Field('text', 'text', 'What it pays for', '', max=80, required=True)),
              max_items=6, group='Your impact'),
        Field('show_inquiry', 'toggle', 'Show the sponsor inquiry form', True, group='Sponsors'),
        Field('inquiry_heading', 'text', 'Inquiry heading', 'Become a Corporate Sponsor', max=60, group='Sponsors'),
        Field('sponsors_heading', 'text', 'Sponsor list heading', 'Our Sponsors', max=60, group='Sponsors'),
        Field('sponsors_empty', 'text', 'When there are no sponsors', 'Support our team and see your logo here!',
              max=120, group='Sponsors'),
        Field('meta_description', 'textarea', 'Search description',
              'Support Mepham Robotics (Team 77628) through donations or corporate sponsorship. Help us build the '
              'future.', max=200, group='Search & sharing'),
    ), page='donate', blurb='Givebutter, levels, impact'),

    Section('contact', 'Contact page', 'mail', (
        Field('hero_title', 'text', 'Big title', 'Contact', max=40, required=True, group='Top of the page'),
        Field('hero_tagline', 'text', 'Tagline', 'Get In Touch', max=80, group='Top of the page'),
        Field('form_title', 'text', 'Form heading', 'Talk to the builders.', max=60, group='Message form'),
        Field('reply_time', 'text', 'Reply promise', 'Usually within 48 hours', max=60, group='Message form'),
        Field('success_text', 'text', 'After sending', 'Message sent. Someone on the team will get back to you.',
              max=160, group='Message form'),
        Field('join_title', 'text', 'Title', 'Future member', max=24, group='"Future member" option'),
        Field('join_subtitle', 'text', 'Subtitle', 'Joining the team', max=30, group='"Future member" option'),
        Field('join_lede', 'textarea', 'Guidance',
              "Tell us your grade and what you're curious about — building, coding, driving, or design. No "
              'experience needed, and you can join mid-season.', max=240, group='"Future member" option'),
        Field('join_label', 'text', 'Message label', 'What would you like to know?', max=60,
              group='"Future member" option'),
        Field('sponsor_title', 'text', 'Title', 'Sponsor', max=24, group='"Sponsor" option'),
        Field('sponsor_subtitle', 'text', 'Subtitle', 'Funding or parts', max=30, group='"Sponsor" option'),
        Field('sponsor_lede', 'textarea', 'Guidance',
              'Let us know what you have in mind — funding, parts, machining time, or mentoring. We can send the '
              "sponsorship packet and this season's budget.", max=240, group='"Sponsor" option'),
        Field('sponsor_label', 'text', 'Message label', 'What would you like to support?', max=60,
              group='"Sponsor" option'),
        Field('general_title', 'text', 'Title', 'Everyone else', max=24, group='"Everyone else" option'),
        Field('general_subtitle', 'text', 'Subtitle', 'Press & outreach', max=30, group='"Everyone else" option'),
        Field('general_lede', 'textarea', 'Guidance',
              'Press, outreach invites, event requests, or anything that does not fit a box. Include dates and a '
              'location if you are inviting us somewhere.', max=240, group='"Everyone else" option'),
        Field('general_label', 'text', 'Message label', 'How can we help?', max=60, group='"Everyone else" option'),
        Field('findus_heading', 'text', 'Heading', '{room}, after the last bell.', max=80, group='Find us'),
        Field('findus_body', 'textarea', 'Text',
              "We're in the tech wing at {school} in North Bellmore. Walk in during any {days_or} meeting — no "
              'appointment, no experience, nothing to bring.', max=500, group='Find us'),
        Field('faq', 'list', 'Questions', [
            {'q': 'How do I join the robotics club?',
             'a': 'Just show up to any of our meetings. We welcome students of all skill levels. You can also email '
                  'us or talk to your guidance counselor.'},
            {'q': 'Do I need prior experience?',
             'a': 'No experience required. We teach everything from basic mechanics to advanced programming. '
                  'Everyone starts somewhere.'},
            {'q': 'What is the time commitment?',
             'a': 'We meet twice a week during the school year. Before competitions, there may be additional '
                  'practice sessions on weekends.'},
            {'q': 'Is there a membership fee?',
             'a': 'No, there is no membership fee to join the Mepham Robotics Club. All students are welcome to '
                  'join for free.'},
            {'q': 'How can my company sponsor the team?',
             'a': "We'd love to hear from you. See the [support page](/donate) for sponsorship levels, or send us a "
                  'message using the form above.'},
            {'q': 'What does a sponsorship actually pay for?',
             'a': 'Competition registration, V5 parts and spares, tools, travel to events, and the materials '
                  'students use to prototype. Parts and machining time are just as welcome as money.'},
            {'q': 'When and where do you meet?',
             'a': 'We meet every {days} from {time} in {room} at {school}.'},
            {'q': 'Can the team come to our event?',
             'a': 'Often, yes. We bring robots to school and community events when the schedule allows. Send the '
                  "date, location, and rough audience size and we'll tell you quickly."},
        ], items=(Field('q', 'text', 'Question', '', max=120, required=True),
                  Field('a', 'rich', 'Answer', '', max=800, required=True)),
              max_items=20, group='Questions'),
        Field('closing_text', 'text', 'Closing line', 'Not ready to write yet?', max=60, group='Questions'),
        Field('meta_description', 'textarea', 'Search description',
              'Contact the Mepham Robotics Club (Team 77628) for inquiries, sponsorship, or membership information.',
              max=200, group='Search & sharing'),
    ), page='contact', blurb='Form, find us, FAQ'),

    Section('achievements', 'Achievements page', 'trophy', (
        Field('hero_title', 'text', 'Big title', 'Achievements', max=40, required=True, group='Top of the page'),
        Field('hero_tagline', 'text', 'Tagline', 'Our Competition History', max=80, group='Top of the page'),
        Field('hero_image', 'image', 'Background photo', None, group='Top of the page'),
        Field('show_stats', 'toggle', 'Show the club record', True, group='Top of the page',
              hint='Awards won, award types, teams and events, counted automatically.'),
        Field('show_featured', 'toggle', 'Show headline honors', True, group='Headline honors',
              hint='Awards styled with a gold border or shimmer on the dashboard.', hint_link=('Awards', 'awards')),
        Field('featured_heading', 'text', 'Heading', 'Headline Honors', max=60, group='Headline honors'),
        Field('awards_heading', 'text', 'Heading', 'All-Time VEX V5 Competition Awards', max=80,
              group='Honor roll', hint='The awards themselves are counted on the dashboard.',
              hint_link=('Awards', 'awards')),
        Field('show_unearned', 'toggle', 'List awards not won yet', True, group='Honor roll'),
        Field('show_teams', 'toggle', 'Show awards by team', True, group='Awards by team',
              hint='One card per robot team with its own award counts.'),
        Field('teams_heading', 'text', 'Heading', 'Awards by Team', max=60, group='Awards by team'),
        Field('show_history', 'toggle', 'Show the competition log', True, group='Competition log',
              hint='Past events from the dashboard, grouped by season.', hint_link=('Events', 'events')),
        Field('history_heading', 'text', 'Heading', 'Competition Log', max=60, group='Competition log'),
        Field('history_limit', 'number', 'How many events to list', 12, min_value=1, max_value=50,
              group='Competition log'),
        Field('show_live', 'toggle', 'Show live match results', True, group='Live results',
              hint='Needs the RobotEvents key; hidden automatically without it.'),
        Field('live_heading', 'text', 'Heading', 'Live Match Results', max=60, group='Live results'),
        Field('live_lede', 'text', 'Text', 'Every match, ranking and skills run from our latest season, straight from RobotEvents',
              max=160, group='Live results'),
        Field('meta_description', 'textarea', 'Search description',
              'Our history of excellence in VEX Robotics competitions, including awards and match results.',
              max=200, group='Search & sharing'),
    ), page='achievements', blurb='Sections, headings, competition log, live results'),

    Section('teams', 'Team pages', 'bot', (
        Field('layout', 'choice', 'Default layout', DEFAULT_TEAM_LAYOUT, choices=TEAM_LAYOUTS, group='Layout',
              hint='Used by every team that has not picked its own layout for the season.'),
        Field('default_tagline', 'text', 'Shown when a team has no nickname', '{tagline}', max=60, group='Layout',
              hint='{tagline} uses the club tagline from Club details.'),
        Field('show_matches', 'toggle', 'Show match results', True, group='Match results',
              hint="The team's matches, rankings and skills for the season shown, from RobotEvents. "
                   'Needs the RobotEvents key; never on the Compact layout or for groups.'),
        Field('matches_heading', 'text', 'Heading', 'Match Results', max=60, group='Match results'),
        Field('cta_show', 'toggle', 'Show the "Interested?" band', True, group='Interested? band'),
        Field('cta_heading', 'text', 'Band heading', 'Interested?', max=60, group='Interested? band'),
        Field('cta_body', 'textarea', 'Band text',
              "Mepham students can join any time — no experience needed. Come find us in the shop, or reach out "
              "and we'll show you around.", max=300, group='Interested? band'),
        Field('cta_button', 'text', 'Band button', 'Join the Club', max=24, group='Interested? band'),
    ), blurb='Shared copy on every team page'),

    Section('footer', 'Footer', 'panel-bottom', (
        Field('newsletter_heading', 'text', 'Newsletter heading', 'Stay Updated', max=40),
        Field('newsletter_blurb', 'text', 'Newsletter text', 'Get competition results and team news in your inbox.',
              max=120),
    ), blurb='Newsletter signup copy'),

    Section('assistant', 'Chat assistant', 'bot-message-square', (
        Field('enabled', 'toggle', 'Show the chat bubble', True,
              hint='Also hidden automatically when the assistant has no API key.'),
        Field('greeting', 'textarea', 'Greeting',
              "Hi there! I'm Steven. I can provide you with information on the Mepham Robotics Club, which focuses "
              'on building, coding, and competing in robotics. How can I assist you today?', max=300),
        Field('knowledge', 'textarea', 'Extra facts for the assistant', '', max=2000,
              hint='Plain sentences the assistant should know, like tryout dates. Never shown on the page.'),
    ), blurb='Greeting and knowledge'),
)

SECTION_MAP = {s.key: s for s in SECTIONS}


def field_for(key):
    """(section, field) for 'section.field', or (None, None)."""
    section_key, _, field_key = (key or '').partition('.')
    section = SECTION_MAP.get(section_key)
    field = section.by_key.get(field_key) if section else None
    return (section, field) if field else (None, None)


# --- Validation ------------------------------------------------------------------

class ContentError(ValueError):
    """A message written for the admin."""


TIME_RE = re.compile(r'([01]\d|2[0-3]):([0-5]\d)')
LINK_RE = re.compile(r'(https?://[^\s<>"]+|mailto:[^\s<>"@]+@[^\s<>"]+|/[^\s<>"]*|#[\w-]*)', re.IGNORECASE)
IMAGE_URL_RE = re.compile(r"https://[A-Za-z0-9.-]+/[A-Za-z0-9._~/%-]+")
IMAGE_MAX_SIDE = 10000


def _text(value, field, multiline=False):
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise ContentError(f'{field.label} must be text.')
    value = value.replace('\r\n', '\n').strip()
    if not multiline:
        value = ' '.join(value.split())
    if field.required and not value:
        raise ContentError(f'{field.label} cannot be empty.')
    if field.max and len(value) > field.max:
        raise ContentError(f'{field.label} must be {field.max} characters or fewer.')
    return value


def _link(value, field):
    value = _text(value, field)
    if value and not LINK_RE.fullmatch(value):
        raise ContentError(f'{field.label} must be a page like /contact, or start with https://.')
    return value


def _image(value, field):
    """An uploaded image {src, width, height} or a built-in photo {key}. None clears it."""
    if value in (None, '', {}):
        if field.required:
            raise ContentError(f'{field.label} is required.')
        return None
    if not isinstance(value, dict):
        raise ContentError(f'{field.label} is not a valid image.')
    if value.get('key'):
        key = str(value['key'])
        if not re.fullmatch(r'photos/[A-Za-z0-9_-]+', key):
            raise ContentError(f'{field.label} is not a valid image.')
        return {'key': key}
    src = str(value.get('src') or '')
    if not IMAGE_URL_RE.fullmatch(src) or len(src) > 500:
        raise ContentError(f'{field.label} must be an uploaded image.')
    try:
        width, height = int(value.get('width')), int(value.get('height'))
    except (TypeError, ValueError):
        raise ContentError(f'{field.label} is missing its size.') from None
    if not (0 < width <= IMAGE_MAX_SIDE and 0 < height <= IMAGE_MAX_SIDE):
        raise ContentError(f'{field.label} has an impossible size.')
    return {'src': src, 'width': width, 'height': height}


def clean_value(field, value):
    """Validate and normalise one value for `field`. Raises ContentError."""
    kind = field.kind
    if kind in ('text', 'email'):
        value = _text(value, field)
        if field.pattern and value and not re.fullmatch(field.pattern, value):
            raise ContentError(f'{field.label} can only use letters, digits, dashes and underscores.')
        if kind == 'email' and value:
            local, _, domain = value.partition('@')
            if not local or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
                raise ContentError('Enter a valid email address.')
        return value
    if kind in ('textarea', 'rich'):
        return _text(value, field, multiline=True)
    if kind == 'url':
        value = _text(value, field)
        if value and not re.match(r'https://[^\s<>"]+$', value, re.IGNORECASE):
            raise ContentError(f'{field.label} must start with https://.')
        return value
    if kind == 'link':
        return _link(value, field)
    if kind == 'toggle':
        if not isinstance(value, bool):
            raise ContentError(f'{field.label} must be on or off.')
        return value
    if kind == 'choice':
        if value not in field.choices:
            raise ContentError(f'Pick one of the listed options for {field.label.lower()}.')
        return value
    if kind == 'time':
        if not isinstance(value, str) or not TIME_RE.fullmatch(value):
            raise ContentError(f'{field.label} must be a time like 15:00.')
        return value
    if kind == 'days':
        if not isinstance(value, list) or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6
                                                  for d in value):
            raise ContentError('Pick meeting days from the list.')
        return sorted(set(value))
    if kind == 'number':
        if value in (None, '') and not field.required and field.default is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int):
            raise ContentError(f'{field.label} must be a whole number.')
        if not field.min_value <= value <= field.max_value:
            raise ContentError(f'{field.label} must be between {field.min_value} and {field.max_value}.')
        return value
    if kind == 'datetime':
        value = _text(value, field)
        if value:
            try:
                datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M')
            except ValueError:
                raise ContentError(f'{field.label} must be a date and time.') from None
        return value
    if kind == 'image':
        return _image(value, field)
    if kind == 'list':
        if not isinstance(value, list):
            raise ContentError(f'{field.label} must be a list.')
        if field.max_items and len(value) > field.max_items:
            raise ContentError(f'{field.label} can have at most {field.max_items} entries.')
        rows = []
        for n, row in enumerate(value, 1):
            if not isinstance(row, dict):
                raise ContentError(f'Entry {n} in {field.label.lower()} is not valid.')
            try:
                cleaned = {item.key: clean_value(item, row.get(item.key, item.default)) for item in field.items}
            except ContentError as e:
                raise ContentError(f'Entry {n}: {e}') from None
            if cleaned.get('starts') and cleaned.get('ends') and cleaned['ends'] < cleaned['starts']:
                raise ContentError(f'Entry {n}: the end must come after the start.')
            rows.append(cleaned)
        if field.key == 'links':
            for n, row in enumerate(rows, 1):
                host = re.sub(r'^https://(www\.)?', '', row['url'].lower()).split('/')[0]
                allowed = SOCIAL_PLATFORMS[row['platform']][2]
                if not any(host == h or host.endswith('.' + h) for h in allowed):
                    raise ContentError(f'Entry {n}: that does not look like a {SOCIAL_PLATFORMS[row["platform"]][0]} '
                                       'link.')
        return rows
    raise ContentError('That field cannot be edited.')


# --- Reading -----------------------------------------------------------------------

def merged(overrides):
    """Every section as a dict of field -> value, overrides on top of defaults."""
    overrides = overrides if isinstance(overrides, dict) else {}
    out = {}
    for section in SECTIONS:
        stored = overrides.get(section.key) if isinstance(overrides.get(section.key), dict) else {}
        out[section.key] = {f.key: stored.get(f.key, f.default) for f in section.fields}
    return out


def warnings(section_key, values, now):
    """Things about a saved section that are allowed but probably not meant.

    These never block a save: times are often changed one at a time, so a
    start can sit after its end for a moment while the admin is mid-edit.
    """
    out = []
    if section_key == 'announcement':
        starts, ends = values.get('starts'), values.get('ends')
        if starts and ends and ends <= starts:
            out.append('"Hide after" is before "Show from", so the announcement will never show.')
        elif values.get('enabled') and _moment(ends) and _moment(ends) < now:
            out.append('"Hide after" has already passed, so the announcement is not showing.')
        elif values.get('enabled') and not (values.get('text') or '').strip():
            out.append('The announcement is on but has no message, so it is not showing.')
    if section_key == 'meeting' and values.get('end', '') <= values.get('start', ''):
        out.append('Meetings end before they start. Set the end time after the start time.')
    return out


# --- Placeholders ------------------------------------------------------------------

# {name}: what it fills in, as the editor lists it. Values come from Club details and
# Meetings, so a room or day change reaches every sentence that names it.
TOKENS = {
    'tagline': 'club tagline',
    'club_name': 'club name',
    'short_name': 'short name',
    'room': 'meeting room',
    'school': 'school',
    'school_short': 'school (short)',
    'days': 'meeting days, like "Tuesday & Friday"',
    'days_or': 'meeting days, like "Tuesday or Friday"',
    'time': 'meeting time, like "3:00–5:00 PM"',
    'schedule': 'days and time together',
}
_TOKEN_RE = re.compile(r'\{(' + '|'.join(TOKENS) + r')\}')


def token_values(values):
    """What each placeholder stands for, from merged (unfilled) values."""
    general, meeting = values['general'], values['meeting']
    days = [DAY_NAMES[d] for d in sorted(meeting['days'])]
    start, end = fmt_time(meeting['start']), fmt_time(meeting['end'])
    if start[-2:] == end[-2:]:
        start = start[:-3]
    return {
        'tagline': general['tagline'], 'club_name': general['club_name'], 'short_name': general['short_name'],
        'room': meeting['room'], 'school': meeting['school'], 'school_short': meeting['school_short'],
        'days': fmt_days(meeting['days']),
        'days_or': ' or '.join(days) if len(days) <= 2 else ', '.join(days[:-1]) + ' or ' + days[-1],
        'time': f'{start}–{end}', 'schedule': fmt_schedule(meeting),
    }


def fill(value, tokens):
    """Placeholders filled in, inside strings, lists and dicts. Unknown {words} stay as typed."""
    if isinstance(value, str):
        return _TOKEN_RE.sub(lambda m: tokens[m.group(1)], value) if '{' in value else value
    if isinstance(value, list):
        return [fill(v, tokens) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, tokens) for k, v in value.items()}
    return value


def filled(values):
    """Merged values with placeholders filled in. Club details and Meetings are where
    the placeholders come from, so they stay as typed."""
    tokens = token_values(values)
    return {key: section if key in ('general', 'meeting') else fill(section, tokens)
            for key, section in values.items()}


class SectionValues(dict):
    """A section's values, readable as attributes in templates (site.home.hero_title)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class SiteContent:
    """Lazy view of the site content: nothing is read until a template touches it.

    `loader` returns the stored overrides dict (or raises; any failure falls
    back to the defaults so a database blip never breaks a page).
    """

    def __init__(self, loader, on_error=None):
        self._loader, self._on_error = loader, on_error
        self._values = None
        self._overrides = None

    def _load(self):
        if self._values is None:
            try:
                self._overrides = self._loader() or {}
            except Exception:
                if self._on_error:
                    self._on_error()
                self._overrides = {}
            values = merged(self._overrides)
            try:
                values = filled(values)
            except Exception:
                if self._on_error:
                    self._on_error()
            self._values = {k: SectionValues(v) for k, v in values.items()}
        return self._values

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        values = self._load()
        if name not in values:
            raise AttributeError(name)
        return values[name]

    def is_custom(self, key):
        self._load()
        section, _, field = key.partition('.')
        return field in (self._overrides.get(section) or {})

    def custom_count(self, section_key):
        self._load()
        return len(self._overrides.get(section_key) or {})


# --- Presentation helpers ------------------------------------------------------------

_BOLD = re.compile(r'\*\*(.+?)\*\*')
_LINK = re.compile(r'\[([^\]\n]{1,120})\]\(([^)\s]{1,300})\)')


def _inline(text):
    """Escape, then allow **bold** and [label](link) with safe link targets only."""
    out, last = [], 0
    for match in _LINK.finditer(text):
        out.append(_BOLD.sub(r'<strong>\1</strong>', str(escape(text[last:match.start()]))))
        label, target = match.group(1), match.group(2)
        label_html = _BOLD.sub(r'<strong>\1</strong>', str(escape(label)))
        if LINK_RE.fullmatch(target):
            external = target.lower().startswith('http')
            attrs = ' target="_blank" rel="noopener"' if external else ''
            out.append(f'<a href="{escape(target)}"{attrs}>{label_html}</a>')
        else:
            out.append(label_html)
        last = match.end()
    out.append(_BOLD.sub(r'<strong>\1</strong>', str(escape(text[last:]))))
    return ''.join(out)


def rich(text, paragraphs=True):
    """Render rich-lite text as HTML: paragraphs on blank lines, <br> on single newlines."""
    text = (text or '').replace('\r\n', '\n').strip()
    if not text:
        return Markup('')
    if not paragraphs:
        return Markup(_inline(' '.join(text.split())))
    blocks = [b.strip() for b in re.split(r'\n\s*\n', text) if b.strip()]
    return Markup(''.join(f'<p>{"<br>".join(_inline(line) for line in block.split(chr(10)))}</p>'
                          for block in blocks))


def fmt_time(hhmm):
    """'15:00' -> '3:00 PM'."""
    hour, minute = (int(p) for p in hhmm.split(':'))
    return f'{(hour - 1) % 12 + 1}:{minute:02d} {"AM" if hour < 12 else "PM"}'


def fmt_days(days):
    names = [DAY_NAMES[d] for d in sorted(days)]
    if len(names) <= 2:
        return ' & '.join(names)
    return ', '.join(names[:-1]) + ' & ' + names[-1]


def fmt_schedule(meeting):
    """'Tuesday & Friday · 3:00–5:00 PM', matching the contact page's original wording."""
    start, end = fmt_time(meeting['start']), fmt_time(meeting['end'])
    if start[-2:] == end[-2:]:
        start = start[:-3]
    return f'{fmt_days(meeting["days"])} · {start}–{end}' if meeting['days'] else f'{start}–{end}'


def social_links(links):
    """Footer/contact rows: (label, icon, url) for each configured platform."""
    return [(SOCIAL_PLATFORMS[r['platform']][0], SOCIAL_PLATFORMS[r['platform']][1], r['url'])
            for r in links or [] if r.get('platform') in SOCIAL_PLATFORMS and r.get('url')]


def announcement_live(announcement, now):
    """True when the announcement is switched on, has text, and `now` is inside its window."""
    if not announcement.get('enabled') or not (announcement.get('text') or '').strip():
        return False
    for key, after in (('starts', True), ('ends', False)):
        value = announcement.get(key)
        if value:
            try:
                moment = datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M')
            except ValueError:
                continue
            if (now < moment) if after else (now > moment):
                return False
    return True


def css_url(src):
    """A stored image URL, safe to place inside url('...') in a style attribute."""
    return src if src and IMAGE_URL_RE.fullmatch(src) else ''


def _moment(value):
    try:
        return datetime.datetime.strptime(value, '%Y-%m-%dT%H:%M') if value else None
    except ValueError:
        return None


def fundraiser_cards(entries, now, limit):
    """Fundraisers for the homepage: not drafts, not over, pinned ones first, then soonest.

    A fundraiser without an end time runs until the end of the day it starts.
    Each card gains `start` and `end` datetimes, `live` (happening now),
    `days_away` and `percent` (None without a goal).
    """
    cards = []
    for entry in entries or []:
        start = _moment(entry.get('starts'))
        if entry.get('hidden') or not entry.get('name') or not start:
            continue
        end = _moment(entry.get('ends'))
        if not end or end < start:
            end = start.replace(hour=23, minute=59)
        if end < now:
            continue
        goal, raised = entry.get('goal'), entry.get('raised')
        percent = min(100, round(100 * (raised or 0) / goal)) if goal else None
        cards.append(dict(entry, start=start, end=end, live=start <= now, percent=percent,
                          days_away=(start.date() - now.date()).days))
    cards.sort(key=lambda c: (not c.get('featured'), c['start']))
    return cards[:limit]
