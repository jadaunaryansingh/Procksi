export const SYSTEM_DEADLINES = {
  teamFormation: new Date('2026-03-10T23:59:59'),
  proposal: new Date('2026-03-15T23:59:59'),
};

export const TODAY = new Date('2026-03-04T10:00:00');

export const MOCK_STUDENT = {
  id: 'STU101',
  name: 'Alex Johnson',
  email: 'alex.j@example.edu',
  avatar: 'https://i.pravatar.cc/150?u=STU101',
  role: 'Student'
};

export const LIFECYCLE_STAGES = [
  { id: 'data', label: 'Student Data' },
  { id: 'team', label: 'Team Formation' },
  { id: 'proposal', label: 'Proposal' },
  { id: 'monitoring', label: 'Monitoring' },
  { id: 'evaluation', label: 'Evaluation' }
];

export const MOCK_NOTIFICATIONS = [
  { id: 1, category: 'Deadlines', title: 'Team Formation Deadline', text: 'Deadline approaching: Team Formation closes in 6 days.', time: '2 hours ago', unread: true },
  { id: 2, category: 'Announcements', title: 'Mentor Assignment', text: 'Mentor assigned: Prof. Sarah Jenkins. Please contact her for scheduled meetings.', time: '1 day ago', unread: false },
  { id: 3, category: 'Decisions', title: 'Proposal Approved', text: 'Your project proposal has been successfully approved by the review committee.', time: '3 days ago', unread: false },
  { id: 4, category: 'Schedules', title: '1st Presentation Scheduled', text: 'Your 1st Presentation is scheduled for 10th April at 10:00 AM in Room 401.', time: '4 days ago', unread: true },
  { id: 5, category: 'Team Requests', title: 'Join Request', text: 'Admin requests you to add student "Jane Doe" (221500123) to your team.', time: 'Just now', unread: true, status: 'pending' },
];

export const MOCK_MILESTONES = [
  { id: 1, title: 'Project Scope & Requirements', deadline: '2026-03-25T23:59:59', status: 'completed', github: 'https://github.com/alexj/procksi-project', file: 'scope_v1.pdf', commits: 12, lastCommit: '2 hours ago' },
  { id: 2, title: 'Mid-Term Presentation', deadline: '2026-04-15T23:59:59', status: 'pending', github: '', file: null, commits: 0, lastCommit: null },
  { id: 3, title: 'Final Code Submission', deadline: '2026-05-10T23:59:59', status: 'pending', github: '', file: null, commits: 0, lastCommit: null },
];

export const MOCK_FEEDBACK = [
  { id: 1, stage: 'Proposal Review', author: 'Prof. Smith', date: '2026-03-18', comments: 'Strong proposal. Ensure you clearly define the AI agents scope. The timeline looks realistic.', grade: 'Approved', status: 'success' },
];

export const MOCK_MENTOR = {
  id: 'MEN101',
  name: 'Prof. Sarah Jenkins',
  department: 'Computer Science and Engineering',
  expertise: ['Artificial Intelligence', 'Machine Learning', 'Data Science'],
  email: 'sarah.jenkins@example.edu',
  phone: '+91-9876543210',
  office: 'Room 304, Academic Block 1',
  availability: 'Mon, Wed, Fri: 2:00 PM - 4:00 PM',
  avatar: 'https://ui-avatars.com/api/?name=Sarah+Jenkins&background=random',
};

export const MOCK_PRESENTATIONS = [
  { id: 1, title: '1st Presentation', status: 'Completed', weightage: '20%', date: '2026-04-10', time: '10:00 AM', location: 'Room 401', isOnline: false, panel: ['Prof. Smith', 'Prof. Davis'], score: 18, maxScore: 20 },
  { id: 2, title: '2nd Presentation', status: 'Scheduled', weightage: '30%', date: '2026-05-15', time: '11:30 AM', location: 'Google Meet', isOnline: true, meetingLink: 'https://meet.google.com/abc-defg-hij', panel: ['Prof. Jenkins', 'Dr. Adams'], score: null, maxScore: 30 },
  { id: 3, title: '3rd Presentation', status: 'Not Scheduled', weightage: '50%', date: 'TBD', time: 'TBD', location: 'TBD', isOnline: false, panel: [], score: null, maxScore: 50 },
];

export const MOCK_EVALUATIONS = {
  currentScore: 82,
  maxPossibleSoFar: 100,
  status: 'Released',
  parameters: [
    { title: 'Problem Understanding', maxMarks: 10, obtained: 9 },
    { title: 'Literature Survey', maxMarks: 20, obtained: 18 },
    { title: 'Methodology Proposed', maxMarks: 30, obtained: 25 },
    { title: 'Presentation Skills', maxMarks: 20, obtained: 16 },
    { title: 'Q&A Handling', maxMarks: 20, obtained: 14 },
  ],
};

export const MOCK_RESULTS = {
  overallScore: 82,
  maxTotalScore: 100,
  grade: 'A',
  status: 'Finalized',
  breakdown: [
    { presentation: '1st Presentation', weightage: '20%', rawScore: '18/20', weightedScore: 18 },
    { presentation: '2nd Presentation', weightage: '30%', rawScore: '26/30', weightedScore: 26 },
    { presentation: '3rd Presentation', weightage: '50%', rawScore: '38/50', weightedScore: 38 },
  ]
};

export const MOCK_EXTRA_ACTIVITIES = [
  { id: 1, title: 'Hackathon Participation', description: 'Participated in the university annual hackathon', date: '2026-02-15', status: 'Verified', points: 50 },
  { id: 2, title: 'Research Paper Publication', description: 'Published a paper in IEEE conference', date: '2026-01-20', status: 'Verified', points: 100 },
  { id: 3, title: 'Tech Workshop', description: 'Attended AWS Cloud Computing workshop', date: '2026-03-05', status: 'Pending Review', points: 0 },
];

export const MOCK_PROBLEM_STATEMENTS = [
  { id: 'PS1', title: 'AI-Powered Resume Analyzer', domain: 'Artificial Intelligence', difficulty: 'Medium', description: 'Build an AI that parses resumes and scores them against job descriptions.' },
  { id: 'PS2', title: 'Smart Campus Parking System', domain: 'IoT', difficulty: 'Hard', description: 'IoT based parking management using camera feeds.' },
  { id: 'PS3', title: 'Decentralized Voting DApp', domain: 'Blockchain', difficulty: 'Hard', description: 'A secure, anonymous voting system built using smart contracts.' },
  { id: 'PS4', title: 'Student Mental Health Chatbot', domain: 'Machine Learning', difficulty: 'Medium', description: 'A supportive chatbot using NLP.' },
  { id: 'PS5', title: 'Real Estate Price Predictor', domain: 'Data Science', difficulty: 'Easy', description: 'Predict housing prices using historical data.' },
];

export const MOCK_ANNOUNCEMENTS = [
  { id: 1, title: 'Project Registration Open', date: '2026-03-01', text: 'Students can now form teams and select their problem statements.' },
  { id: 2, title: 'Guidelines Updated', date: '2026-03-03', text: 'The project evaluation parameters have been updated. Check the portal for details.' }
];
