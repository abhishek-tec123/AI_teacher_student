"""
Preference Management Module

Handles all preference-related operations including:
- Subject preference management
- Learning progress tracking
- Preference updates and normalization
- Quiz performance integration
- Common mistakes and confusion tracking
"""

from bson import ObjectId
from datetime import datetime
from typing import Dict, Any, Optional, List
from common.db.database import DatabaseConnection, DEFAULT_SUBJECT_PREFERENCE, normalize_student_preference


class PreferenceManager:
    """
    Manages student learning preferences and progress tracking.
    
    Provides functionality for managing subject-specific preferences,
    learning progress, quiz performance, and confusion tracking.
    """
    
    def __init__(self, db_connection: DatabaseConnection = None):
        """Initialize preference manager with database connection."""
        self.db = db_connection or DatabaseConnection()
        self.students = self.db.get_students_collection()
    
    def get_or_create_subject_preference(self, student_id: str, subject: str) -> Dict[str, Any]:
        """
        Get or create subject preference for a student.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Subject preference dictionary with default values applied
            
        Raises:
            ValueError: If student not found
        """
        # Find student using student_id
        doc = self.students.find_one(
            {"student_id": student_id},
            {"subject_preferences": 1}
        )

        # If student doesn't exist → raise error
        if not doc:
            raise ValueError(f"Student '{student_id}' not found.")

        subject_preferences = doc.get("subject_preferences", {})

        # If subject preference doesn't exist → create default
        if subject not in subject_preferences:
            default_subject_pref = dict(DEFAULT_SUBJECT_PREFERENCE)

            self.students.update_one(
                {"student_id": student_id},
                {"$set": {f"subject_preferences.{subject}": default_subject_pref}}
            )

            subject_preferences[subject] = default_subject_pref

        # Always return canonical schema
        merged = {
            **DEFAULT_SUBJECT_PREFERENCE,
            **subject_preferences[subject]
        }

        return merged
    
    def update_subject_preference(
        self, 
        student_id: str, 
        subject: str, 
        updates: Dict[str, Any]
    ) -> int:
        """
        Update specific subject preferences (partial update).
        
        Args:
            student_id: Student identifier
            subject: Subject name
            updates: Dictionary of preference updates
            
        Returns:
            Number of modified documents
        """
        if not updates:
            return 0

        update_fields = {
            f"subject_preferences.{subject}.{k}": v
            for k, v in updates.items()
        }

        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": update_fields}
        )

        return result.modified_count
    
    def set_subject_preference(
        self, 
        student_id: str, 
        subject: str, 
        preference: Dict[str, Any]
    ) -> int:
        """
        Set entire subject preference (complete replacement).
        
        Args:
            student_id: Student identifier
            subject: Subject name
            preference: Complete preference dictionary
            
        Returns:
            Number of modified documents
        """
        # Normalize preference with defaults
        normalized_pref = normalize_student_preference(preference.copy())
        
        result = self.students.update_one(
            {"student_id": student_id},
            {"$set": {f"subject_preferences.{subject}": normalized_pref}}
        )
        return result.modified_count
    
    def get_all_subject_preferences(self, student_id: str) -> Dict[str, Any]:
        """
        Get all subject preferences for a student.
        
        Args:
            student_id: Student identifier
            
        Returns:
            Dictionary of all subject preferences
        """
        doc = self.students.find_one(
            {"student_id": student_id},
            {"subject_preferences": 1}
        )
        
        if not doc:
            return {}
        
        subject_preferences = doc.get("subject_preferences", {})
        
        # Apply default values to all subjects
        normalized_preferences = {}
        for subject, pref in subject_preferences.items():
            normalized_preferences[subject] = {
                **DEFAULT_SUBJECT_PREFERENCE,
                **pref
            }
        
        return normalized_preferences
    
    def update_confusion_counter(
        self, 
        student_id: str, 
        subject: str, 
        confusion_type: str
    ) -> int:
        """
        Update confusion counter for a specific confusion type.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            confusion_type: Type of confusion
            
        Returns:
            Number of modified documents
        """
        # Ensure subject preference exists
        self.get_or_create_subject_preference(student_id, subject)
        
        result = self.students.update_one(
            {"student_id": student_id},
            {
                "$inc": {
                    f"subject_preferences.{subject}.confusion_counter.{confusion_type}": 1
                }
            }
        )
        
        return result.modified_count
    
    def get_confusion_counters(
        self, 
        student_id: str, 
        subject: str
    ) -> Dict[str, int]:
        """
        Get confusion counters for a subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Dictionary of confusion counters
        """
        preference = self.get_or_create_subject_preference(student_id, subject)
        return preference.get("confusion_counter", {})
    
    def add_common_mistake(
        self, 
        student_id: str, 
        subject: str, 
        mistake: str
    ) -> int:
        """
        Add a common mistake for a student in a subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            mistake: Description of the common mistake
            
        Returns:
            Number of modified documents
        """
        # Ensure subject preference exists
        self.get_or_create_subject_preference(student_id, subject)
        
        result = self.students.update_one(
            {"student_id": student_id},
            {
                "$addToSet": {
                    f"subject_preferences.{subject}.common_mistakes": mistake
                }
            }
        )
        
        return result.modified_count
    
    def remove_common_mistake(
        self, 
        student_id: str, 
        subject: str, 
        mistake: str
    ) -> int:
        """
        Remove a common mistake for a student in a subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            mistake: Description of the common mistake to remove
            
        Returns:
            Number of modified documents
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {
                "$pull": {
                    f"subject_preferences.{subject}.common_mistakes": mistake
                }
            }
        )
        
        return result.modified_count
    
    def update_quiz_performance(
        self, 
        student_id: str, 
        subject: str, 
        score: int, 
        total_questions: int = 5
    ) -> int:
        """
        Update quiz performance tracking.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            score: Quiz score achieved
            total_questions: Total number of questions in quiz
            
        Returns:
            Number of modified documents
        """
        # Ensure subject preference exists
        self.get_or_create_subject_preference(student_id, subject)
        
        # Calculate percentage
        percentage = (score / total_questions) * 100
        
        # Add to score history
        result = self.students.update_one(
            {"student_id": student_id},
            {
                "$push": {
                    f"subject_preferences.{subject}.quiz_score_history": {
                        "score": score,
                        "total_questions": total_questions,
                        "percentage": percentage,
                        "timestamp": datetime.utcnow()
                    }
                }
            }
        )
        
        # Update consecutive counters
        if percentage >= 80:  # Good performance
            self.students.update_one(
                {"student_id": student_id},
                {
                    "$inc": {
                        f"subject_preferences.{subject}.consecutive_perfect_scores": 1
                    },
                    "$set": {
                        f"subject_preferences.{subject}.consecutive_low_scores": 0
                    }
                }
            )
        elif percentage < 60:  # Poor performance
            self.students.update_one(
                {"student_id": student_id},
                {
                    "$inc": {
                        f"subject_preferences.{subject}.consecutive_low_scores": 1
                    },
                    "$set": {
                        f"subject_preferences.{subject}.consecutive_perfect_scores": 0
                    }
                }
            )
        else:  # Average performance - reset counters
            self.students.update_one(
                {"student_id": student_id},
                {
                    "$set": {
                        f"subject_preferences.{subject}.consecutive_perfect_scores": 0,
                        f"subject_preferences.{subject}.consecutive_low_scores": 0
                    }
                }
            )
        
        return result.modified_count
    
    def get_quiz_performance_summary(
        self, 
        student_id: str, 
        subject: str
    ) -> Dict[str, Any]:
        """
        Get quiz performance summary for a student in a subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Dictionary with quiz performance statistics
        """
        preference = self.get_or_create_subject_preference(student_id, subject)
        
        score_history = preference.get("quiz_score_history", [])
        consecutive_perfect = preference.get("consecutive_perfect_scores", 0)
        consecutive_low = preference.get("consecutive_low_scores", 0)
        
        if not score_history:
            return {
                "total_quizzes": 0,
                "average_score": 0,
                "average_percentage": 0,
                "best_score": 0,
                "best_percentage": 0,
                "consecutive_perfect_scores": consecutive_perfect,
                "consecutive_low_scores": consecutive_low,
                "recent_trend": "no_data"
            }
        
        # Calculate statistics
        total_quizzes = len(score_history)
        total_score = sum(quiz["score"] for quiz in score_history)
        total_percentage = sum(quiz["percentage"] for quiz in score_history)
        best_quiz = max(score_history, key=lambda x: x["percentage"])
        
        # Determine recent trend (last 3 quizzes)
        recent_trend = "stable"
        if len(score_history) >= 3:
            recent_quizzes = score_history[-3:]
            percentages = [quiz["percentage"] for quiz in recent_quizzes]
            if all(percentages[i] <= percentages[i+1] for i in range(len(percentages)-1)):
                recent_trend = "improving"
            elif all(percentages[i] >= percentages[i+1] for i in range(len(percentages)-1)):
                recent_trend = "declining"
        
        return {
            "total_quizzes": total_quizzes,
            "average_score": total_score / total_quizzes,
            "average_percentage": total_percentage / total_quizzes,
            "best_score": best_quiz["score"],
            "best_percentage": best_quiz["percentage"],
            "consecutive_perfect_scores": consecutive_perfect,
            "consecutive_low_scores": consecutive_low,
            "recent_trend": recent_trend,
            "last_quiz": score_history[-1] if score_history else None
        }
    
    def reset_preference_counters(
        self, 
        student_id: str, 
        subject: str
    ) -> int:
        """
        Reset confusion and quiz performance counters for a subject.
        
        Args:
            student_id: Student identifier
            subject: Subject name
            
        Returns:
            Number of modified documents
        """
        result = self.students.update_one(
            {"student_id": student_id},
            {
                "$set": {
                    f"subject_preferences.{subject}.confusion_counter": {},
                    f"subject_preferences.{subject}.quiz_score_history": [],
                    f"subject_preferences.{subject}.consecutive_low_scores": 0,
                    f"subject_preferences.{subject}.consecutive_perfect_scores": 0
                }
            }
        )
        
        return result.modified_count
    
    def get_preference_summary(
        self, 
        student_id: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive preference summary for a student.
        
        Args:
            student_id: Student identifier
            
        Returns:
            Dictionary with preference statistics across all subjects
        """
        all_preferences = self.get_all_subject_preferences(student_id)
        
        summary = {
            "total_subjects": len(all_preferences),
            "subjects": {},
            "overall_stats": {
                "total_confusion_types": set(),
                "total_common_mistakes": 0,
                "total_quizzes": 0,
                "subjects_with_perfect_streak": 0,
                "subjects_with_low_streak": 0
            }
        }
        
        for subject, pref in all_preferences.items():
            confusion_counters = pref.get("confusion_counter", {})
            common_mistakes = pref.get("common_mistakes", [])
            quiz_history = pref.get("quiz_score_history", [])
            consecutive_perfect = pref.get("consecutive_perfect_scores", 0)
            consecutive_low = pref.get("consecutive_low_scores", 0)
            
            # Update overall stats
            summary["overall_stats"]["total_confusion_types"].update(confusion_counters.keys())
            summary["overall_stats"]["total_common_mistakes"] += len(common_mistakes)
            summary["overall_stats"]["total_quizzes"] += len(quiz_history)
            
            if consecutive_perfect >= 2:
                summary["overall_stats"]["subjects_with_perfect_streak"] += 1
            if consecutive_low >= 2:
                summary["overall_stats"]["subjects_with_low_streak"] += 1
            
            # Subject-specific summary
            summary["subjects"][subject] = {
                "learning_style": pref.get("learning_style", "step-by-step"),
                "response_length": pref.get("response_length", "long"),
                "include_example": pref.get("include_example", True),
                "confusion_types_count": len(confusion_counters),
                "common_mistakes_count": len(common_mistakes),
                "quiz_count": len(quiz_history),
                "consecutive_perfect_scores": consecutive_perfect,
                "consecutive_low_scores": consecutive_low,
                "has_quiz_data": len(quiz_history) > 0
            }
        
        # Convert set to count
        summary["overall_stats"]["total_confusion_types"] = len(summary["overall_stats"]["total_confusion_types"])
        
        return summary
