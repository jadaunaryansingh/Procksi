import { apiUpsertTable } from './api';

// Audit logging utility for tracking all system activities
export class AuditLogger {
    static async log(user, action, severity = 'medium') {
        try {
            const auditEntry = {
                user: user || 'system',
                action,
                severity: severity.toLowerCase(), // high, medium, low
                time: new Date().toISOString().replace('T', ' ').substring(0, 19) + ' UTC'
            };

            await apiUpsertTable('governance_audit', [auditEntry], null);
        } catch (error) {
            console.error('Failed to log audit entry:', error);
        }
    }

    // Specific logging methods for different types of actions
    static async logSystemAction(action) {
        await this.log('system', action, 'low');
    }

    static async logAdminAction(user, action) {
        await this.log(user, action, 'high');
    }

    static async logUserAction(user, action) {
        await this.log(user, action, 'medium');
    }

    static async logSecurityEvent(action) {
        await this.log('security_monitor', action, 'high');
    }

    static async logMentorAction(user, action) {
        await this.log(user, action, 'medium');
    }

    static async logTeamAction(user, action) {
        await this.log(user, action, 'medium');
    }

    static async logScheduleAction(user, action) {
        await this.log(user, action, 'medium');
    }

    static async logProposalAction(user, action) {
        await this.log(user, action, 'medium');
    }
}

// Helper function to get current user (you might need to adjust this based on your auth system)
export function getCurrentUser() {
    // This should return the current logged-in user
    // For now, returning 'admin' as placeholder
    return 'admin';
}
