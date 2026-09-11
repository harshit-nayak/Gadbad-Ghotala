import { ORG_DOMAIN } from '../app/brand';
import type { Office, Person } from '../domain/types';

const person = (p: Omit<Person, 'initials' | 'email'> & { location: Office }): Person => ({
  ...p,
  initials: p.name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2),
  email: `${p.name.toLowerCase().replace(/\s+/g, '.')}@${ORG_DOMAIN}`,
});

/** Organisation directory used across the prototype. */
export const people = {
  rahulSharma: person({
    id: 'emp-0001',
    name: 'Rahul Sharma',
    role: 'Chief Executive Officer',
    roleShort: 'CEO',
    department: 'Leadership',
    location: 'Mumbai',
    mobile: '+91 98201 47365',
    officialLine: '+91 22 4000 1000',
  }),
  anilKapoor: person({
    id: 'emp-0002',
    name: 'Anil Kapoor',
    role: 'Chief Financial Officer',
    roleShort: 'CFO',
    department: 'Leadership',
    location: 'Mumbai',
    mobile: '+91 98190 22614',
    officialLine: '+91 22 4000 1002',
  }),
  deepakVerma: person({
    id: 'emp-0003',
    name: 'Deepak Verma',
    role: 'Chief Technology Officer',
    roleShort: 'CTO',
    department: 'Leadership',
    location: 'Bengaluru',
    mobile: '+91 98450 71132',
    officialLine: '+91 80 4600 1003',
  }),
  vikramRao: person({
    id: 'emp-0011',
    name: 'Vikram Rao',
    role: 'HR Director',
    roleShort: 'HR Director',
    department: 'HR & Payroll',
    location: 'Hyderabad',
    mobile: '+91 98490 30418',
    officialLine: '+91 40 4400 1011',
  }),
  priyaMenon: person({
    id: 'emp-0417',
    name: 'Priya Menon',
    role: 'Finance Manager',
    roleShort: 'Finance Manager',
    department: 'Finance',
    location: 'Mumbai',
  }),
  arjunMehta: person({ id: 'emp-0522', name: 'Arjun Mehta', role: 'Treasury Analyst', roleShort: 'Treasury', department: 'Treasury', location: 'Mumbai' }),
  nehaIyer: person({ id: 'emp-0610', name: 'Neha Iyer', role: 'Procurement Lead', roleShort: 'Procurement', department: 'Procurement', location: 'Bengaluru' }),
  kavyaNair: person({ id: 'emp-0733', name: 'Kavya Nair', role: 'Payroll Executive', roleShort: 'Payroll', department: 'HR & Payroll', location: 'Chennai' }),
  sanaQureshi: person({ id: 'emp-0815', name: 'Sana Qureshi', role: 'IT Administrator', roleShort: 'IT Admin', department: 'IT', location: 'Delhi NCR' }),
  rohanDas: person({ id: 'emp-0902', name: 'Rohan Das', role: 'Accounts Payable Executive', roleShort: 'Accounts Payable', department: 'Finance', location: 'Kolkata' }),
  meeraJoshi: person({ id: 'emp-0958', name: 'Meera Joshi', role: 'Legal Counsel', roleShort: 'Legal', department: 'Legal', location: 'Pune' }),
  farhanSheikh: person({ id: 'emp-1044', name: 'Farhan Sheikh', role: 'Sales Operations Manager', roleShort: 'Sales Ops', department: 'Sales', location: 'Delhi NCR' }),
  lakshmiReddy: person({ id: 'emp-1120', name: 'Lakshmi Reddy', role: 'Vendor Payments Officer', roleShort: 'Vendor Payments', department: 'Finance', location: 'Hyderabad' }),
};

/** Security team members who act on incidents. */
export const analysts = {
  farahKhan: 'Farah Khan, SOC Lead',
  nikhilBansal: 'Nikhil Bansal, Fraud Analyst',
  ishaGupta: 'Isha Gupta, Security Analyst',
};

/** Sign-in identity used for actions taken in the Security workspace. */
export const currentAnalyst = analysts.nikhilBansal;
export const currentAdmin = 'Sunita Pillai, Administrator';

export const directory: Person[] = Object.values(people);
