/**
 * steps.js
 *
 * Step data for the mentor first-login walkthrough. Data only, no JSX, so
 * the overlay stays presentational and these are easy to reorder or reword.
 *
 * `anchor` matches a `data-tour="..."` attribute in the DOM. A step whose
 * anchor is not on the page is skipped rather than rendered against a null
 * rect -- a mentor with no assigned teams may never render the stat cards.
 *
 * `placement` is a preference, not a guarantee: the overlay flips a tooltip
 * that would land off-screen.
 *
 * Deliberately excluded: GitHub Analytics Hub, Presentations, History and
 * PMS-Chat. This is orientation -- it names where things live rather than
 * teaching every screen. PMS-Chat additionally sits behind PMS_CHAT_ENABLED
 * and is a disabled, greyed-out nav item in production, so a step pointing
 * at it would highlight something the mentor cannot click.
 */

/** Steps shown on a full-size viewport. */
export const DESKTOP_STEPS = [
    {
        id: 'welcome',
        anchor: null, // centered modal -- see note below
        title: 'Welcome to the Mentor Portal',
        body: 'A quick tour of where everything lives. It takes about a minute, and you can skip it at any point.',
    },
    {
        id: 'sidebar',
        anchor: 'sidebar-nav',
        placement: 'right',
        title: 'Your navigation',
        body: 'Every section of the portal is here. The rail collapses if you want more room -- hover to bring it back.',
    },
    {
        id: 'stat-teams',
        anchor: 'stat-total-teams',
        placement: 'bottom',
        title: 'Teams assigned to you',
        body: 'The projects you are mentoring this semester.',
    },
    {
        id: 'stat-proposals',
        anchor: 'stat-pending-proposals',
        placement: 'bottom',
        title: 'Waiting on you',
        body: 'Synopses your teams have submitted that still need a decision. When this is above zero, something needs your attention.',
    },
    {
        id: 'nav-teams',
        anchor: 'nav-teams',
        placement: 'right',
        title: 'My Teams',
        body: 'Open any team to see its members, its problem statement, and its GitHub repository.',
    },
    {
        id: 'nav-milestones',
        anchor: 'nav-milestones',
        placement: 'right',
        title: 'Synopsis Submissions',
        body: 'Review what your teams submit and either approve it or send it back with feedback.',
    },
    {
        id: 'nav-evaluation',
        anchor: 'nav-evaluation',
        placement: 'right',
        title: 'Evaluations',
        body: 'Where you submit marks for a team. Once an evaluation is submitted it is final, so review it before you confirm.',
    },
];

/**
 * Steps shown below the `md` breakpoint.
 *
 * The sidebar is a drawer on mobile, so its nav items are unmounted and
 * cannot be highlighted. Rather than pointing at elements that are not
 * there, the four sidebar steps collapse into one that explains the menu.
 */
export const MOBILE_STEPS = [
    DESKTOP_STEPS[0],
    {
        id: 'mobile-menu',
        anchor: 'mobile-menu-button',
        placement: 'bottom',
        title: 'Your navigation',
        body: 'Teams, synopsis submissions and evaluations all live in this menu.',
    },
    DESKTOP_STEPS[2],
    DESKTOP_STEPS[3],
];
