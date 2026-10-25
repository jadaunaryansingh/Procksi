import { TODAY } from '../data/mockData';

export const getCountdown = (deadlineDate) => {
    const diff = new Date(deadlineDate) - TODAY;
    if (diff <= 0) return "Deadline passed";
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
    return `${days}d ${hours}h remaining`;
};
