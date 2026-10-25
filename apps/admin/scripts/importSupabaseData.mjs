import fs from 'fs';
import path from 'path';
import xlsx from 'xlsx';
import { createClient } from '@supabase/supabase-js';

const projectRoot = process.cwd();
const envPath = path.join(projectRoot, '.env');
const excelPath = path.join(projectRoot, '3rd AIML + IOT 2nd Presentation Marks (1).xlsx');

function parseEnv(filePath) {
    const env = {};
    if (!fs.existsSync(filePath)) return env;

    const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/);
    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#') || !trimmed.includes('=')) continue;
        const idx = trimmed.indexOf('=');
        const key = trimmed.slice(0, idx).trim();
        const value = trimmed.slice(idx + 1).trim();
        env[key] = value;
    }
    return env;
}

function chunk(items, size = 250) {
    const chunks = [];
    for (let i = 0; i < items.length; i += size) chunks.push(items.slice(i, i + size));
    return chunks;
}

function normalizeDomain(title = '') {
    const t = title.toLowerCase();
    if (t.includes('iot')) return 'IoT';
    if (t.includes('ai') || t.includes('ml') || t.includes('deepfake')) return 'AI/ML';
    if (t.includes('web') || t.includes('app') || t.includes('portal')) return 'Web Dev';
    return 'AI/ML';
}

function normalizeBranch(section = '') {
    const sec = section.toUpperCase();
    if (sec.includes('IOT')) return 'B.Tech IoT';
    if (sec.includes('AI')) return 'B.Tech AI/ML';
    return 'B.Tech CS';
}

async function upsertTable(supabase, tableName, rows, onConflict) {
    if (!rows.length) return;
    for (const batch of chunk(rows)) {
        const { error } = await supabase.from(tableName).upsert(batch, { onConflict });
        if (error) {
            throw new Error(`${tableName}: ${error.message}`);
        }
    }
}

function buildDatasets(worksheetRows, semesterId) {
    let currentTeamNo = null;
    const teams = new Map();

    worksheetRows.forEach((row) => {
        const parsedTeamNo = row['Team No'];
        if (parsedTeamNo !== null && parsedTeamNo !== undefined && parsedTeamNo !== '') {
            currentTeamNo = Number(parsedTeamNo);
        }

        if (!currentTeamNo) return;

        const teamCode = `TEAM-${currentTeamNo}`;
        const memberName = (row['Member Name'] || '').toString().trim();
        const roll = (row['Roll Number'] || '').toString().trim();
        const section = (row['Section'] || '').toString().trim();
        const email = (row['Email ID'] || '').toString().trim();
        const projectTitle = (row['Project Statement'] || '').toString().trim();
        const mentor = (row['Mentor'] || '').toString().trim();
        const panel = (row['Panel'] || '').toString().trim();

        if (!teams.has(teamCode)) {
            teams.set(teamCode, {
                teamCode,
                teamNo: currentTeamNo,
                title: projectTitle || `Capstone Project ${currentTeamNo}`,
                mentor: mentor || 'TBD',
                panel: panel || 'Panel A',
                domain: normalizeDomain(projectTitle),
                members: [],
            });
        }

        const team = teams.get(teamCode);
        if (projectTitle) team.title = projectTitle;
        if (mentor) team.mentor = mentor;
        if (panel) team.panel = panel;

        if (memberName || roll) {
            team.members.push({
                id: roll || `${teamCode}-${team.members.length + 1}`,
                name: memberName || `Student ${team.members.length + 1}`,
                roll: roll || `${teamCode}-${team.members.length + 1}`,
                branch: normalizeBranch(section),
                section,
                email,
            });
        }
    });

    const teamList = Array.from(teams.values());

    const students = teamList.flatMap((team) => team.members.map((m) => ({
        id: m.id,
        name: m.name,
        email: m.email,
        year: 3,
        branch: m.branch,
        section: m.section,
        status: 'Active',
        semester_id: semesterId,
    })));

    const teamsValidation = teamList.map((team) => ({
        id: team.teamCode,
        title: team.title,
        description: team.title,
        leader: team.members[0]?.name || 'TBD',
        domain: team.domain,
        mentor: team.mentor,
        memberCount: team.members.length,
        validationStatus: 'Pending',
        semester_id: semesterId,
        members: team.members.map((m) => ({
            id: m.id,
            name: m.name,
            roll: m.roll,
            branch: m.branch,
        })),
    }));

    const mentorAllocations = teamList.map((team) => ({
        id: team.teamCode,
        title: team.title,
        domain: team.domain,
        aiRecommended: team.mentor,
        assignedMentor: team.mentor && team.mentor !== 'TBD' ? [team.mentor] : [],
        semester_id: semesterId,
    }));

    const proposals = teamList.map((team, i) => ({
        id: `PROP-${1000 + i}`,
        teamId: team.teamCode,
        title: team.title,
        aiScore: 70 + (i % 25),
        aiRationale: 'Imported from AIML/IOT dataset. Review can be updated by admin.',
        status: 'Pending',
        submittedDate: `2026-04-${String((i % 28) + 1).padStart(2, '0')}`,
        semester_id: semesterId,
    }));

    const results = teamList.map((team, i) => ({
        team: team.teamCode,
        title: team.title,
        domain: team.domain,
        branch: team.members[0]?.branch?.includes('IoT') ? 'IOT' : 'AIML',
        proposalMarks: null,
        midMarks: null,
        finalMarks: null,
        totalScore: null,
        mentor: team.mentor,
        semester_id: semesterId,
    }));

    const mentorNames = [...new Set(teamList.map((t) => t.mentor).filter(Boolean))];
    const mentors = mentorNames.map((name, i) => ({
        id: `M-${String(i + 1).padStart(3, '0')}`,
        name,
        email: null,
        domain: ['AI/ML', 'IoT', 'Web Dev'][i % 3],
        load: teamList.filter((t) => t.mentor === name).length,
        maxLoad: 8,
        color: ['blue', 'emerald', 'rose', 'amber'][i % 4],
        teams: teamList.filter((t) => t.mentor === name).length,
    }));

    const panelNames = [...new Set(teamList.map((t) => t.panel).filter(Boolean))];
    const panels = panelNames.map((name, i) => ({
        id: `P-${String(i + 1).padStart(3, '0')}`,
        name,
        description: 'Imported panel group',
        members: [],
        teams: teamList.filter((t) => t.panel === name).length,
    }));

    const scheduleSlots = teamList.slice(0, 12).map((team, i) => ({
        date: `2026-05-${String((i % 10) + 15).padStart(2, '0')}`,
        time: `${10 + (i % 6)}:00 AM - ${10 + (i % 6)}:30 AM`,
        team: team.teamCode,
        panel: team.panel,
        room: i % 2 === 0 ? 'Seminar Hall 1' : 'Lab 402',
        capacity: 30,
        meetLink: null,
        semester_id: semesterId,
    }));

    const evaluationQueue = teamList.slice(0, 10).map((team, i) => ({
        id: `EVAL-${i + 1}`,
        team: team.teamCode,
        type: i % 2 === 0 ? 'Mid-Term Review' : 'Final Presentation',
        evaluator: team.panel,
        timeStr: `${10 + (i % 8)}:${i % 2 === 0 ? '00' : '30'} AM`,
        status: 'Pending',
        semester_id: semesterId,
    }));

    const evaluationFeed = teamList.slice(0, 5).map((team, i) => ({
        id: `FEED-${i + 1}`,
        team: team.teamCode,
        evaluator: team.mentor,
        score: 80 + (i % 15),
        timeAgo: `${(i + 1) * 10} mins ago`,
        semester_id: semesterId,
    }));

    return {
        students,
        proposals,
        teamsValidation,
        mentorAllocations,
        mentors,
        panels,
        results,
        scheduleSlots,
        evaluationQueue,
        evaluationFeed,
    };
}

async function main() {
    const fileEnv = parseEnv(envPath);

    const supabaseUrl = process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL || fileEnv.SUPABASE_URL || fileEnv.VITE_SUPABASE_URL;
    const serviceKey =
        process.env.SUPABASE_SERVICE_ROLE_KEY ||
        process.env.SUPABASE_SECRET_KEY ||
        fileEnv.SUPABASE_SERVICE_ROLE_KEY ||
        fileEnv.SUPABASE_SECRET_KEY;

    if (!supabaseUrl || !serviceKey) {
        throw new Error('Missing SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SECRET_KEY) in environment.');
    }

    if (!fs.existsSync(excelPath)) {
        throw new Error(`Excel file not found: ${excelPath}`);
    }

    const workbook = xlsx.readFile(excelPath);
    const firstSheet = workbook.SheetNames[0];
    const rows = xlsx.utils.sheet_to_json(workbook.Sheets[firstSheet], { defval: null });

    const supabase = createClient(supabaseUrl, serviceKey, { auth: { persistSession: false } });

    // Fetch the active semester ID
    let semesterId = null;
    const { data: activeSems, error: semError } = await supabase
        .from('semester_config')
        .select('id')
        .eq('is_active', true);
        
    if (semError) {
        console.error('Error fetching active semester:', semError.message);
    } else if (activeSems && activeSems.length > 0) {
        semesterId = activeSems[0].id;
        console.log(`Using active semester: ${semesterId}`);
    } else {
        // Fallback: try to get any semester config
        const { data: allSems } = await supabase.from('semester_config').select('id');
        if (allSems && allSems.length > 0) {
            semesterId = allSems[0].id;
            console.log(`No active semester found. Using first available semester: ${semesterId}`);
        } else {
            console.warn('WARNING: No semester configurations found in semester_config. Imported data will have semester_id = null.');
        }
    }

    const datasets = buildDatasets(rows, semesterId);

    await upsertTable(supabase, 'students', datasets.students, 'id');
    await upsertTable(supabase, 'proposals', datasets.proposals, 'id');
    await upsertTable(supabase, 'teams_validation', datasets.teamsValidation, 'id');
    await upsertTable(supabase, 'mentor_allocations', datasets.mentorAllocations, 'id');
    await upsertTable(supabase, 'mentors', datasets.mentors, 'id');
    await upsertTable(supabase, 'panels', datasets.panels, 'id');
    await upsertTable(supabase, 'results', datasets.results, 'team');

    const { error: scheduleClearError } = await supabase.from('schedule_slots').delete().neq('id', -1);
    if (scheduleClearError) throw new Error(`schedule_slots clear failed: ${scheduleClearError.message}`);
    const { error: queueClearError } = await supabase.from('evaluation_queue').delete().neq('id', '');
    if (queueClearError) throw new Error(`evaluation_queue clear failed: ${queueClearError.message}`);
    const { error: feedClearError } = await supabase.from('evaluation_feed').delete().neq('id', '');
    if (feedClearError) throw new Error(`evaluation_feed clear failed: ${feedClearError.message}`);

    for (const batch of chunk(datasets.scheduleSlots)) {
        const { error } = await supabase.from('schedule_slots').insert(batch);
        if (error) throw new Error(`schedule_slots insert failed: ${error.message}`);
    }

    await upsertTable(supabase, 'evaluation_queue', datasets.evaluationQueue, 'id');
    await upsertTable(supabase, 'evaluation_feed', datasets.evaluationFeed, 'id');

    console.log(`Imported ${datasets.students.length} students from ${rows.length} spreadsheet rows.`);
    console.log(`Upserted ${datasets.teamsValidation.length} teams, ${datasets.proposals.length} proposals, ${datasets.mentors.length} mentors.`);
}

main().catch((error) => {
    console.error('Import failed:', error.message);
    process.exit(1);
});
