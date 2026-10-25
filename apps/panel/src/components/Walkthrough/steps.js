/**
 * steps.js -- Panel Portal walkthrough.
 *
 * Two kinds of tour:
 *
 *   TOUR_STEPS.overview  the first-login orientation, naming each section
 *   TOUR_STEPS['/panel/slots'] etc.  a per-page tour for that route
 *
 * The overview runs once on first login. A page tour runs the first time a
 * panel member opens that page, and can be replayed from the help button in
 * the header, which always offers the tour for whatever page is showing.
 *
 * `anchor` matches a `data-tour="..."` attribute. A step whose anchor is not
 * in the DOM is skipped rather than rendered against a null rect, so empty
 * states (no slots scheduled, no missed submissions) degrade to a shorter
 * tour instead of a broken one.
 *
 * PMS-Chat has no steps: it sits behind PMS_CHAT_ENABLED and is a disabled,
 * greyed-out nav item in production.
 */

const overview = [
    {
        id: 'welcome',
        anchor: null,
        title: 'Welcome to the Panel Portal',
        body: 'This is where you evaluate the teams assigned to your panel. A quick tour of where everything lives -- you can skip it at any point.',
    },
    {
        id: 'sidebar',
        anchor: 'sidebar-nav',
        placement: 'right',
        title: 'Your navigation',
        body: 'Every section of the portal is here. The rail collapses if you want more room.',
    },
    {
        id: 'nav-my-teams',
        anchor: 'nav-my-teams',
        placement: 'right',
        title: 'My Teams',
        body: 'The teams assigned to your panel, and how far you have got with each one.',
    },
    {
        id: 'nav-slots',
        anchor: 'nav-slots',
        placement: 'right',
        title: 'My Slots',
        body: 'Your evaluation schedule. Each slot is a team, a time, and a link to join.',
    },
    {
        id: 'nav-parameters',
        anchor: 'nav-parameters',
        placement: 'right',
        title: 'Parameters',
        body: 'The criteria you score against, and what each one is worth.',
    },
    {
        id: 'nav-missed',
        anchor: 'nav-missed',
        placement: 'right',
        title: 'Missed',
        body: 'Teams that did not submit in time. The administrator is notified automatically.',
    },
];

const dashboard = [
    {
        id: 'home-intro',
        anchor: null,
        title: 'Your dashboard',
        body: 'This page answers one question: what should you be doing right now?',
    },
    {
        id: 'home-live',
        anchor: 'panel-live-slot',
        placement: 'bottom',
        title: 'Live slot',
        body: 'The evaluation happening now. Join the meeting straight from here -- and if a session overruns, you will be offered the option to extend it.',
    },
    {
        id: 'home-next',
        anchor: 'panel-next-up',
        placement: 'bottom',
        title: 'Next up',
        body: 'The slot immediately after the current one, so you know who is coming.',
    },
    {
        id: 'home-progress',
        anchor: 'panel-progress',
        placement: 'top',
        title: 'Your progress',
        body: 'Assigned, completed and pending across the whole panel.',
    },
];

const slots = [
    {
        id: 'slots-intro',
        anchor: null,
        title: 'My Slots',
        body: 'Your evaluation schedule, in the order you will work through it.',
    },
    {
        id: 'slots-table',
        anchor: 'panel-slots-table',
        placement: 'top',
        title: 'The schedule',
        body: 'Each row is one team: its time slot, its current status, and the action available to you.',
    },
    {
        id: 'slots-action',
        anchor: 'panel-slots-action',
        placement: 'left',
        title: 'Starting an evaluation',
        body: 'Open a team from here to score it. Where a meeting link exists, Join Meet takes you straight into the call.',
    },
];

const myTeams = [
    {
        id: 'teams-intro',
        anchor: null,
        title: 'My Teams',
        body: 'Everything assigned to your panel, with progress at a glance.',
    },
    {
        id: 'teams-progress',
        anchor: 'panel-teams-progress',
        placement: 'bottom',
        title: 'Evaluation progress',
        body: 'How many of your teams are done and how many are still pending.',
    },
    {
        id: 'teams-filter',
        anchor: 'panel-teams-filter',
        placement: 'bottom',
        title: 'Finding a team',
        body: 'Search by name, or filter down to just the ones still waiting on you.',
    },
];

const parameters = [
    {
        id: 'params-intro',
        anchor: null,
        title: 'Parameters',
        body: 'The criteria every team is scored against.',
    },
    {
        id: 'params-list',
        anchor: 'panel-params-list',
        placement: 'top',
        title: 'The criteria',
        body: 'Each row is one criterion and the marks available for it. These are set centrally, so every panel scores on the same basis.',
    },
    {
        id: 'params-total',
        anchor: 'panel-params-total',
        placement: 'top',
        title: 'Total marks',
        body: 'What the criteria add up to. Worth checking before you start a round of evaluations.',
    },
];

const missed = [
    {
        id: 'missed-intro',
        anchor: null,
        title: 'Missed submissions',
        body: 'Teams that did not submit before their deadline.',
    },
    {
        id: 'missed-totals',
        anchor: 'panel-missed-totals',
        placement: 'bottom',
        title: 'The scale of it',
        body: 'How many submissions were missed, and how many separate teams that involves.',
    },
    {
        id: 'missed-list',
        anchor: 'panel-missed-list',
        placement: 'top',
        title: 'Who and what',
        body: 'The teams and the specific deliverables involved. The administrator is notified automatically, so this page is for your awareness rather than an action list.',
    },
];

/** Route path -> steps. `overview` is the first-login orientation. */
export const TOUR_STEPS = {
    overview,
    '/panel': dashboard,
    '/panel/slots': slots,
    '/panel/my-teams': myTeams,
    '/panel/parameters': parameters,
    '/panel/missed': missed,
};

/** Human label for each page tour, shown in the help button tooltip. */
export const TOUR_LABELS = {
    '/panel': 'dashboard',
    '/panel/slots': 'slots',
    '/panel/my-teams': 'teams',
    '/panel/parameters': 'parameters',
    '/panel/missed': 'missed submissions',
};
