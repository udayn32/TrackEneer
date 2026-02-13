"""
NSGA-II (Non-dominated Sorting Genetic Algorithm II) Study Schedule Generator

This module implements a multi-objective optimization algorithm to generate
optimal study schedules based on exam timetables.

Objectives:
1. Minimize cramming (spread study sessions evenly)
2. Minimize context switching (reduce subject changes)
3. Maximize revision effectiveness (prioritize subjects with upcoming exams)
"""

import random
import re
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from copy import deepcopy


@dataclass
class StudyGene:
    """Represents a single study session in the chromosome"""
    day: int
    subject_index: int
    hours: int


@dataclass
class Individual:
    """Represents an individual solution in the population"""
    chromosome: List[StudyGene]
    objectives: Dict[str, float] = field(default_factory=dict)
    rank: int = 0
    crowding_distance: float = 0.0


@dataclass
class ExamInfo:
    """Normalized exam information"""
    paper_name: str
    date: Optional[datetime]
    days_until: int = 999


class NSGA2Config:
    """Configuration for NSGA-II algorithm"""
    POPULATION_SIZE = 100
    GENERATIONS = 150
    CROSSOVER_RATE = 0.9
    MUTATION_RATE = 0.1
    STUDY_HOURS_PER_DAY = 8
    SESSIONS_PER_DAY_MIN = 2
    SESSIONS_PER_DAY_MAX = 4
    DEFAULT_STUDY_DAYS = 60  # 2 months
    DAY_START_HOUR = 9
    DAY_END_HOUR = 22  # last hour for study window


class PaperNameCleaner:
    """Clean and normalize paper names from OCR output"""
    
    # Common OCR artifacts to remove
    OCR_ARTIFACTS = [
        r'\s*-\s*P\s*$',           # " - P" at end
        r'\s*-\s*P\.\s*$',         # " - P." at end  
        r'\s*-\s*P\s+P\s*$',       # " - P P" at end
        r'\s*P\s*P\s*$',           # "P P" at end
        r'\s*-\s*PAM\s*$',         # " - PAM" at end (artifact)
        r'\s+P\s*$',               # " P" at end
        r'\s+P\.\s*$',             # " P." at end
        r'\s*-\s*P\s+[A-Z0-9]*$',  # " - P [anything]" at end
    ]
    
    # Course code patterns to extract and remove from paper name
    CODE_PATTERNS = [
        r'\s*-\s*null\s*$',                                    # "- null" (literal null)
        r'\s*-\s*P\s+[A-Z]*[Ii][Oo][Tt][A-Z0-9]*\d+[A-Z0-9]*\s*$',  # "- P loTCSBCC701", "- P IoTCSBCC701"
        r'\s*-\s*[Ii][Oo][Tt][A-Z0-9]*\d{3,}[A-Z0-9]*\s*$',  # "- IoTCSBCC503", "- IoTCSBCDLOS5013"
        r'\s*-\s*[A-Z]{2,}[A-Z0-9]*\d{3,}[A-Z0-9]*\s*$',     # "- TCSBCC701", "- HAIMLC701", "- HAIMLCS01"
        r'\s*-\s*[A-Z]+\d{3,}\s*$',                           # "- OEC301", "- ILO7016"
        r'\s*-\s*\d{4,}\s*$',                                 # "- 153111", "- 2153112" (pure numeric codes)
        r'\s*-\s*P\s*[A-Z0-9]+\s*$',                          # "- P xyz" variants
    ]
    
    @classmethod
    def clean(cls, paper_name: str, subject: str = "") -> str:
        """
        Clean paper name without extracting course code
        
        Returns: cleaned_paper_name
        """
        if not paper_name:
            return subject or "Unknown Subject"
        
        text = str(paper_name).strip()
        
        # Remove course codes at the end
        for pattern in cls.CODE_PATTERNS:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Remove OCR artifacts
        for artifact in cls.OCR_ARTIFACTS:
            text = re.sub(artifact, '', text, flags=re.IGNORECASE)
        
        # Clean up remaining artifacts
        text = re.sub(r'\s*-\s*$', '', text)  # Trailing dash
        text = re.sub(r'\s+', ' ', text)       # Multiple spaces
        text = text.strip(' -.')
        
        # If text is empty or too short, use subject
        if len(text) < 3:
            text = subject.strip() if subject else "Unknown Subject"
        
        # Combine subject prefix if needed and not already present
        if subject and subject.strip():
            subject_clean = subject.strip()
            if not text.lower().startswith(subject_clean.lower()[:5]):
                # Check if subject adds meaningful info
                if len(subject_clean) > 2 and subject_clean.lower() not in text.lower():
                    text = f"{subject_clean} {text}"
        
        return text.strip()


class NSGA2Scheduler:
    """NSGA-II based study schedule optimizer"""
    
    def __init__(self, config: NSGA2Config = None):
        self.config = config or NSGA2Config()
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str:
            return None
        
        # Try ISO format first
        try:
            if 'T' in str(date_str):
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            # Try YYYY-MM-DD
            match = re.match(r'(\d{4})-(\d{2})-(\d{2})', str(date_str))
            if match:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except:
            pass
        return None
    
    def _normalize_exams(self, exams: List[Dict], start_date: datetime) -> List[ExamInfo]:
        """Normalize exam data for processing"""
        normalized = []
        
        for exam in exams:
            # Clean paper name
            paper = exam.get('paper', exam.get('paper_name', ''))
            subject = exam.get('subject', '')
            
            cleaned_name = PaperNameCleaner.clean(paper, subject)
            
            # Parse date
            date_str = exam.get('date', '')
            exam_date = self._parse_date(date_str)
            
            # Calculate days until exam
            if exam_date:
                raw_days = (exam_date - start_date).days
                # If the exam is in the past, treat as distant (not urgent)
                days_until = raw_days if raw_days > 0 else 999
            else:
                days_until = 999
            
            normalized.append(ExamInfo(
                paper_name=cleaned_name,
                date=exam_date,
                days_until=days_until
            ))
        
        return normalized
    
    def _create_random_chromosome(self, num_days: int, num_subjects: int) -> List[StudyGene]:
        """Create a random chromosome (study schedule)"""
        chromosome = []
        safe_num_subjects = max(1, num_subjects)
        
        for day in range(num_days):
            # 2-4 study sessions per day
            sessions = random.randint(
                self.config.SESSIONS_PER_DAY_MIN,
                self.config.SESSIONS_PER_DAY_MAX
            )
            
            for _ in range(sessions):
                chromosome.append(StudyGene(
                    day=day,
                    subject_index=random.randint(0, safe_num_subjects - 1),
                    hours=random.randint(1, 3)
                ))
        
        return chromosome
    
    def _evaluate_objectives(
        self, 
        chromosome: List[StudyGene], 
        exams: List[ExamInfo],
        start_date: datetime
    ) -> Dict[str, float]:
        """
        Evaluate the three objectives for NSGA-II:
        1. Cramming score (lower is better - more evenly distributed)
        2. Switching cost (lower is better - fewer subject changes)
        3. Revision score (lower is better - negative of effectiveness)
        """
        cramming_score = 0.0
        switching_cost = 0.0
        revision_score = 0.0
        
        subject_study_days: Dict[str, List[Dict]] = {}
        prev_subject = None
        
        for gene in chromosome:
            if gene.subject_index < 0 or gene.subject_index >= len(exams):
                continue
            
            exam = exams[gene.subject_index]
            subject = exam.paper_name
            
            # Track study distribution
            if subject not in subject_study_days:
                subject_study_days[subject] = []
            subject_study_days[subject].append({
                'day': gene.day,
                'hours': gene.hours
            })
            
            # Switching cost
            if prev_subject and prev_subject != subject:
                switching_cost += 1
            prev_subject = subject
            
            # Revision score: studying closer to exam is more valuable
            if exam.date:
                current_day = start_date + timedelta(days=gene.day)
                days_until_exam = max(1, (exam.date - current_day).days)
                # Exponential decay: studying 1-3 days before is most valuable
                import math
                revision_score += gene.hours * math.exp(-days_until_exam / 7)
        
        # Calculate cramming score (variance of study distribution)
        for days_list in subject_study_days.values():
            if len(days_list) < 2:
                cramming_score += 10  # Penalize single-day cramming
            else:
                gaps = []
                sorted_days = sorted(days_list, key=lambda x: x['day'])
                for i in range(1, len(sorted_days)):
                    gaps.append(sorted_days[i]['day'] - sorted_days[i-1]['day'])
                
                if gaps:
                    avg_gap = sum(gaps) / len(gaps)
                    variance = sum((g - avg_gap) ** 2 for g in gaps) / len(gaps)
                    cramming_score += variance
        
        return {
            'cramming': cramming_score,
            'switching': switching_cost,
            'revision': -revision_score  # Negative because we maximize revision
        }
    
    def _dominates(self, a: Individual, b: Individual) -> bool:
        """Check if solution A dominates solution B (Pareto dominance)"""
        dominated = False
        strictly_better = False
        
        for key in a.objectives:
            if a.objectives[key] > b.objectives[key]:
                dominated = True
            if a.objectives[key] < b.objectives[key]:
                strictly_better = True
        
        return strictly_better and not dominated
    
    def _non_dominated_sort(self, population: List[Individual]) -> List[List[int]]:
        """Perform non-dominated sorting on the population"""
        n = len(population)
        domination_count = [0] * n
        dominated_solutions: List[List[int]] = [[] for _ in range(n)]
        fronts: List[List[int]] = [[]]
        
        for i in range(n):
            for j in range(i + 1, n):
                if self._dominates(population[i], population[j]):
                    dominated_solutions[i].append(j)
                    domination_count[j] += 1
                elif self._dominates(population[j], population[i]):
                    dominated_solutions[j].append(i)
                    domination_count[i] += 1
            
            if domination_count[i] == 0:
                population[i].rank = 0
                fronts[0].append(i)
        
        front_index = 0
        while fronts[front_index]:
            next_front = []
            for i in fronts[front_index]:
                for j in dominated_solutions[i]:
                    domination_count[j] -= 1
                    if domination_count[j] == 0:
                        population[j].rank = front_index + 1
                        next_front.append(j)
            front_index += 1
            fronts.append(next_front)
        
        return fronts[:-1] if fronts[-1] == [] else fronts
    
    def _calculate_crowding_distance(self, population: List[Individual], front: List[int]):
        """Calculate crowding distance for individuals in a front"""
        n = len(front)
        if n <= 2:
            for i in front:
                population[i].crowding_distance = float('inf')
            return
        
        for i in front:
            population[i].crowding_distance = 0
        
        objectives = list(population[0].objectives.keys())
        
        for obj in objectives:
            # Sort by objective value
            sorted_front = sorted(front, key=lambda x: population[x].objectives[obj])
            
            # Boundary points get infinite distance
            population[sorted_front[0]].crowding_distance = float('inf')
            population[sorted_front[-1]].crowding_distance = float('inf')
            
            min_val = population[sorted_front[0]].objectives[obj]
            max_val = population[sorted_front[-1]].objectives[obj]
            range_val = max_val - min_val if max_val != min_val else 1
            
            for i in range(1, n - 1):
                prev_val = population[sorted_front[i-1]].objectives[obj]
                next_val = population[sorted_front[i+1]].objectives[obj]
                population[sorted_front[i]].crowding_distance += (next_val - prev_val) / range_val
    
    def _tournament_select(self, population: List[Individual]) -> Individual:
        """Binary tournament selection"""
        i = random.randint(0, len(population) - 1)
        j = random.randint(0, len(population) - 1)
        
        if population[i].rank < population[j].rank:
            return population[i]
        if population[j].rank < population[i].rank:
            return population[j]
        
        return population[i] if population[i].crowding_distance > population[j].crowding_distance else population[j]
    
    def _crossover(self, parent1: Individual, parent2: Individual) -> Tuple[Individual, Individual]:
        """Uniform crossover"""
        if random.random() > self.config.CROSSOVER_RATE:
            return deepcopy(parent1), deepcopy(parent2)
        
        child1_chromosome = []
        child2_chromosome = []
        
        min_len = min(len(parent1.chromosome), len(parent2.chromosome))
        
        for i in range(min_len):
            if random.random() < 0.5:
                child1_chromosome.append(deepcopy(parent1.chromosome[i]))
                child2_chromosome.append(deepcopy(parent2.chromosome[i]))
            else:
                child1_chromosome.append(deepcopy(parent2.chromosome[i]))
                child2_chromosome.append(deepcopy(parent1.chromosome[i]))
        
        return (
            Individual(chromosome=child1_chromosome),
            Individual(chromosome=child2_chromosome)
        )
    
    def _mutate(self, individual: Individual, num_subjects: int) -> Individual:
        """Mutation operator"""
        mutated = Individual(chromosome=[deepcopy(g) for g in individual.chromosome])
        safe_num_subjects = max(1, num_subjects)
        
        for gene in mutated.chromosome:
            if random.random() < self.config.MUTATION_RATE:
                if random.random() < 0.5:
                    # Mutate subject
                    gene.subject_index = random.randint(0, safe_num_subjects - 1)
                else:
                    # Mutate hours
                    gene.hours = max(1, min(
                        self.config.STUDY_HOURS_PER_DAY,
                        gene.hours + random.choice([-1, 1])
                    ))
        
        return mutated
    
    def generate_schedule(self, exams: List[Dict]) -> Dict:
        """
        Main entry point: Generate optimized study schedule using NSGA-II
        
        Args:
            exams: List of exam dictionaries with 'paper', 'subject', 'date' fields
        
        Returns:
            Dictionary containing the generated schedule
        """
        if not exams:
            return {'error': 'No exams provided', 'schedule': []}
        
        start_date = datetime.now()
        normalized_exams = self._normalize_exams(exams, start_date)
        num_subjects = len(normalized_exams)
        
        # Calculate study period
        earliest_exam = min((e.date for e in normalized_exams if e.date), default=None)
        if earliest_exam:
            num_days = min(
                self.config.DEFAULT_STUDY_DAYS,
                max(14, (earliest_exam - start_date).days)
            )
        else:
            num_days = self.config.DEFAULT_STUDY_DAYS
        
        # Initialize population
        population: List[Individual] = []
        for _ in range(self.config.POPULATION_SIZE):
            chromosome = self._create_random_chromosome(num_days, num_subjects)
            objectives = self._evaluate_objectives(chromosome, normalized_exams, start_date)
            population.append(Individual(chromosome=chromosome, objectives=objectives))
        
        # Track convergence
        best_balanced_score = float('inf')
        convergence_gen = 0

        # Evolution loop
        for gen in range(self.config.GENERATIONS):
            # Non-dominated sorting
            fronts = self._non_dominated_sort(population)
            
            # Update convergence tracking
            if population:
                try:
                    # Quick proxy for balanced score: sum of raw objectives
                    current_best = min(population, key=lambda x: sum(x.objectives.values()))
                    current_score = sum(current_best.objectives.values())
                    if current_score < best_balanced_score:
                        best_balanced_score = current_score
                        convergence_gen = gen
                except:
                    pass
            
            # Calculate crowding distance
            for front in fronts:
                self._calculate_crowding_distance(population, front)
            
            # Create offspring
            offspring: List[Individual] = []
            while len(offspring) < self.config.POPULATION_SIZE:
                parent1 = self._tournament_select(population)
                parent2 = self._tournament_select(population)
                child1, child2 = self._crossover(parent1, parent2)
                
                child1 = self._mutate(child1, num_subjects)
                child2 = self._mutate(child2, num_subjects)
                
                child1.objectives = self._evaluate_objectives(
                    child1.chromosome, normalized_exams, start_date
                )
                child2.objectives = self._evaluate_objectives(
                    child2.chromosome, normalized_exams, start_date
                )
                
                offspring.extend([child1, child2])
            
            # Combine parent and offspring
            combined = population + offspring[:self.config.POPULATION_SIZE]
            combined_fronts = self._non_dominated_sort(combined)
            for front in combined_fronts:
                self._calculate_crowding_distance(combined, front)
            
            # Select next generation
            population = []
            for front in combined_fronts:
                if len(population) + len(front) <= self.config.POPULATION_SIZE:
                    for i in front:
                        population.append(combined[i])
                else:
                    # Sort by crowding distance and fill remaining
                    sorted_front = sorted(
                        front,
                        key=lambda x: combined[x].crowding_distance,
                        reverse=True
                    )
                    for i in sorted_front:
                        if len(population) >= self.config.POPULATION_SIZE:
                            break
                        population.append(combined[i])
                    break
        
        # Get Pareto front
        pareto_front = [ind for ind in population if ind.rank == 0]
        if not pareto_front:
            pareto_front = population
        
        # Strategy: Pick 3 distinct solutions
        # 1. Balanced: Minimum sum of standardized objectives
        # 2. Low Stress: Minimum cramming score
        # 3. High Focus: Minimum switching cost
        
        cramming_vals = [ind.objectives['cramming'] for ind in pareto_front]
        switching_vals = [ind.objectives['switching'] for ind in pareto_front]
        revision_vals = [ind.objectives['revision'] for ind in pareto_front]
        
        # Helper to normalize
        def normalize(val, vals):
            if max(vals) == min(vals): return 0
            return (val - min(vals)) / (max(vals) - min(vals))
            
        # Select assignments
        balanced_solution = min(
            pareto_front,
            key=lambda x: (
                normalize(x.objectives['cramming'], cramming_vals) + 
                normalize(x.objectives['switching'], switching_vals) + 
                normalize(x.objectives['revision'], revision_vals)
            )
        )
        
        low_stress_solution = min(pareto_front, key=lambda x: x.objectives['cramming'])
        high_focus_solution = min(pareto_front, key=lambda x: x.objectives['switching'])
        
        # Ensure we have a list of unique solutions objects (even if content is same)
        solutions_map = {
            'balanced': balanced_solution,
            'low_stress': low_stress_solution,
            'high_focus': high_focus_solution
        }
        
        # Convert all unique solutions
        results = []
        seen_ids = set()
        
        start_date_iso = start_date.isoformat()

        # Order matters for UI
        for key, label in [('balanced', 'Balanced Plan'), ('low_stress', 'Low Stress (Even Spread)'), ('high_focus', 'High Focus (Min Switching)')]:
            sol = solutions_map[key]
            
            # Simple dedup based on objective signature to avoid 3 identical tabs if algorithm converged heavily
            sig = (sol.objectives['cramming'], sol.objectives['switching'], sol.objectives['revision'])
            # We allow duplicates if it makes UI clearer, but maybe flag them?
            # actually better to just return them, UI can handle or user sees they are same.
            
            schedule = self._convert_to_schedule(
                sol,
                normalized_exams,
                start_date,
                num_days
            )
            
            results.append({
                'id': key,
                'label': label,
                'schedule': schedule,
                'num_days': num_days,
                'num_subjects': num_subjects,
                'start_date': start_date_iso,
                'objectives': sol.objectives
            })
            
        return {
            'schedules': results,
            'debug_info': {
                'generations': self.config.GENERATIONS,
                'population_size': self.config.POPULATION_SIZE,
                'convergence_generation': convergence_gen
            }
        }
    
    def _generate_study_tasks(self, hours: int, days_until_exam: int) -> List[Dict]:
        """Generate study tasks based on proximity to exam"""
        tasks = []
        
        if days_until_exam > 30:
            # Early phase: concept learning
            tasks.append({'task': 'Read textbook chapters', 'duration': max(1, int(hours * 0.4)), 'type': 'learn'})
            tasks.append({'task': 'Watch video lectures', 'duration': max(1, int(hours * 0.3)), 'type': 'learn'})
            tasks.append({'task': 'Make summary notes', 'duration': max(1, int(hours * 0.3)), 'type': 'notes'})
        elif days_until_exam > 14:
            # Mid phase: practice
            tasks.append({'task': 'Review notes', 'duration': max(1, int(hours * 0.2)), 'type': 'review'})
            tasks.append({'task': 'Solve practice problems', 'duration': max(1, int(hours * 0.5)), 'type': 'practice'})
            tasks.append({'task': 'Create flashcards', 'duration': max(1, int(hours * 0.3)), 'type': 'notes'})
        elif days_until_exam > 3:
            # Final phase: revision
            tasks.append({'task': 'Quick revision', 'duration': max(1, int(hours * 0.3)), 'type': 'review'})
            tasks.append({'task': 'Solve past papers', 'duration': max(1, int(hours * 0.5)), 'type': 'practice'})
            tasks.append({'task': 'Review weak topics', 'duration': max(1, int(hours * 0.2)), 'type': 'review'})
        else:
            # Last days: final prep
            tasks.append({'task': 'Flashcard review', 'duration': max(1, int(hours * 0.3)), 'type': 'review'})
            tasks.append({'task': 'Formula/key points revision', 'duration': max(1, int(hours * 0.4)), 'type': 'review'})
            tasks.append({'task': 'Light practice', 'duration': max(1, int(hours * 0.3)), 'type': 'practice'})
        
        return tasks
    
    def _convert_to_schedule(
        self,
        solution: Individual,
        exams: List[ExamInfo],
        start_date: datetime,
        num_days: int
    ) -> List[Dict]:
        """Convert NSGA-II solution to a readable schedule format"""
        schedule = []
        
        # Group genes by day
        day_groups: Dict[int, List[StudyGene]] = {}
        for gene in solution.chromosome:
            if gene.day not in day_groups:
                day_groups[gene.day] = []
            day_groups[gene.day].append(gene)
        
        for day in range(num_days):
            current_date = start_date + timedelta(days=day)
            sessions = day_groups.get(day, [])
            
            day_schedule = {
                'date': current_date.isoformat(),
                'date_label': current_date.strftime('%a, %b %d'),
                'is_weekend': current_date.weekday() >= 5,
                'sessions': []
            }
            
            # Consolidate sessions by subject
            subject_hours: Dict[str, int] = {}
            for gene in sessions:
                if 0 <= gene.subject_index < len(exams):
                    subject = exams[gene.subject_index].paper_name
                    subject_hours[subject] = subject_hours.get(subject, 0) + gene.hours
            
            start_hour = self.config.DAY_START_HOUR
            used_hours = 0
            for subject, hours in subject_hours.items():
                exam = next((e for e in exams if e.paper_name == subject), None)
                days_until = exam.days_until if exam else 999
                
                # Adjust days_until based on current day
                if exam and exam.date:
                    raw_days = (exam.date - current_date).days
                    days_until = raw_days if raw_days > 0 else 999
                
                # Determine priority (avoid past-exam urgent labeling)
                if days_until == 999:
                    priority = 'past'
                elif days_until <= 3:
                    priority = 'high'
                elif days_until <= 7:
                    priority = 'medium'
                else:
                    priority = 'normal'

                # Respect daily study window limits
                remaining_today = max(0, self.config.STUDY_HOURS_PER_DAY - used_hours)
                allowed = min(hours, remaining_today)
                if allowed <= 0:
                    continue
                
                end_hour = start_hour + allowed
                # Clamp to the end of study window
                if end_hour > self.config.DAY_END_HOUR:
                    allowed = max(0, self.config.DAY_END_HOUR - start_hour)
                    end_hour = start_hour + allowed
                if allowed <= 0:
                    break
                
                day_schedule['sessions'].append({
                    'subject': subject,
                    'hours': allowed,
                    'start_time': f'{start_hour:02d}:00',
                    'end_time': f'{end_hour:02d}:00',
                    'priority': priority,
                    'days_until_exam': days_until,
                    'tasks': self._generate_study_tasks(allowed, days_until)
                })
                
                used_hours += allowed
                start_hour = min(end_hour + 1, self.config.DAY_END_HOUR)
            
            schedule.append(day_schedule)
        
        return schedule


# Convenience function for direct use
def generate_study_schedule(exams: List[Dict]) -> Dict:
    """Generate an optimized study schedule using NSGA-II"""
    scheduler = NSGA2Scheduler()
    return scheduler.generate_schedule(exams)


# Clean paper name function for external use
def clean_paper_name(paper: str, subject: str = "") -> str:
    """Clean a paper name, removing OCR artifacts and course codes"""
    return PaperNameCleaner.clean(paper, subject)
