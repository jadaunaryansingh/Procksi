/**
 * steps.js -- Student Portal walkthrough.
 *
 * Two kinds of tour:
 *
 *   TOUR_STEPS.overview  the first-login orientation, naming the main sections
 *   TOUR_STEPS['/student/team'] etc.  a per-page tour for that route
 *
 * The overview runs once on first login. A page tour runs the first time a
 * student opens that page, and can be replayed from the help button, which
 * always offers the tour for whatever page is showing.
 *
 * `anchor` matches a `data-tour="..."` attribute. A step whose anchor is not
 * in the DOM is skipped rather than rendered against a null rect. This
 * matters more here than in the other portals: a student with no team, no
 * mentor and no released results sees a lot of empty states, and each of
 * those simply shortens the tour.
 *
 * The sidebar has twelve entries. The overview names the five that carry
 * real work rather than reciting all twelve -- orientation should leave a
 * student knowing where to start, not make them memorise a menu.
 *
 * PMS-Chat has no steps: it sits behind PMS_CHAT_ENABLED and is a disabled,
 * greyed-out nav item in production.
 */

const overview = [
    {
        id: 'welcome',
        anchor: null,
        title: 'Welcome to your project portal',
        body: 'This is where your team, your submissions and your results all live. A quick tour -- you can skip it at any point.',
    },
    {
        id: 'sidebar',
        anchor: 'sidebar-nav',
        placement: 'right',
        title: 'Your navigation',
        body: 'Every section is here. The rail collapses if you want more room on screen.',
    },
    {
        id: 'nav-team',
        anchor: 'nav-team',
        placement: 'right',
        title: 'Team',
        body: 'Form your team and manage its members. Most things in this portal only unlock once you have a team.',
    },
    {
        id: 'nav-preferences',
        anchor: 'nav-preferences',
        placement: 'right',
        title: 'Project Preferences',
        body: 'Browse problem statements and reserve the one your team wants to work on.',
    },
    {
        id: 'nav-milestones',
        anchor: 'nav-milestones',
        placement: 'right',
        title: 'Synopsis Submission',
        body: 'Whatever your mentor asks you to submit shows up here, with its deadline.',
    },
    {
        id: 'nav-presentations',
        anchor: 'nav-presentations',
        placement: 'right',
        title: 'Presentation Schedule',
        body: 'When and where you present to the evaluation panel.',
    },
    {
        id: 'nav-results',
        anchor: 'nav-results',
        placement: 'right',
        title: 'Results',
        body: 'Your scores and final grade, once the coordinator releases them.',
    },
];

const dashboard = [
    {
        id: 'dash-intro',
        anchor: null,
        title: 'Your dashboard',
        body: 'A summary of where your project stands right now.',
    },
    {
        id: 'dash-status',
        anchor: 'student-status-cards',
        placement: 'bottom',
        title: 'Your current status',
        body: 'Your team, your mentor and your repository at a glance. Anything still unset is shown plainly, so you can see what to sort out next.',
    },
    {
        id: 'dash-deadlines',
        anchor: 'student-deadlines',
        placement: 'top',
        title: 'Deadlines',
        body: 'What is due and when. A deadline disappears from here once it has passed, so this stays a list of things you can still act on.',
    },
    {
        id: 'dash-announcements',
        anchor: 'student-announcements',
        placement: 'top',
        title: 'Announcements',
        body: 'Notices from your coordinator.',
    },
];

const team = [
    {
        id: 'team-intro',
        anchor: null,
        title: 'Your team',
        body: 'Forming a team is the first step -- most other sections stay locked until this is done.',
    },
    {
        id: 'team-members',
        anchor: 'student-team-members',
        placement: 'bottom',
        title: 'Members',
        body: 'Everyone on the team, with the leader marked. Empty slots show how many more people you can add.',
    },
    {
        id: 'team-add',
        anchor: 'student-team-add',
        placement: 'left',
        title: 'Adding a member',
        body: 'Invite a classmate by email. They need to accept before they count as part of the team.',
    },
];

const preferences = [
    {
        id: 'pref-intro',
        anchor: null,
        title: 'Project Preferences',
        body: 'Where your team chooses the problem statement it will work on.',
    },
    {
        id: 'pref-browse',
        anchor: 'student-pref-browse',
        placement: 'bottom',
        title: 'Browse and reserve',
        body: 'Look through the available problem statements and filter by domain. Reserving one holds it for your team.',
    },
    {
        id: 'pref-submission',
        anchor: 'student-pref-submission',
        placement: 'top',
        title: 'Your submission',
        body: 'Upload your proposal here. If the coordinator sends it back, their remarks appear on this page -- read them before resubmitting.',
    },
];

const milestones = [
    {
        id: 'mile-intro',
        anchor: null,
        title: 'Synopsis Submission',
        body: 'Everything your mentor has asked the team to submit.',
    },
    {
        id: 'mile-progress',
        anchor: 'student-milestone-progress',
        placement: 'bottom',
        title: 'Your progress',
        body: 'How many requests you have completed, and how many are still open.',
    },
    {
        id: 'mile-list',
        anchor: 'student-milestone-list',
        placement: 'top',
        title: 'The requests',
        body: 'Each one carries its own deadline and its own form. Submit before the deadline -- a closed request cannot be reopened from here.',
    },
];

const mentor = [
    {
        id: 'mentor-intro',
        anchor: null,
        title: 'Your mentor',
        body: 'Who is supervising your project, and how to reach them.',
    },
    {
        id: 'mentor-contact',
        anchor: 'student-mentor-contact',
        placement: 'bottom',
        title: 'Contact details',
        body: 'Their email and, where they have set them, their office hours. If no mentor is shown yet, allocation has not happened -- that is done centrally, not by you.',
    },
];

const results = [
    {
        id: 'results-intro',
        anchor: null,
        title: 'Results',
        body: 'Your scores, once they have been released.',
    },
    {
        id: 'results-score',
        anchor: 'student-results-score',
        placement: 'bottom',
        title: 'Your score',
        body: 'Your overall score and final grade. Until the coordinator releases results, this page will tell you they are not out yet rather than showing a partial mark.',
    },
];

/** Route path -> steps. `overview` is the first-login orientation. */
export const TOUR_STEPS = {
    overview,
    '/student/dashboard': dashboard,
    '/student/team': team,
    '/student/preferences': preferences,
    '/student/milestones': milestones,
    '/student/mentor': mentor,
    '/student/results': results,
};

/** Human label for each page tour, shown in the help button tooltip. */
export const TOUR_LABELS = {
    '/student/dashboard': 'dashboard',
    '/student/team': 'team',
    '/student/preferences': 'project preferences',
    '/student/milestones': 'synopsis submission',
    '/student/mentor': 'mentor',
    '/student/results': 'results',
};
