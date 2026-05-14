# import sys
# import os
# from run_single_queryFun import run_query

#     os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
# )
# import logging
# from teacher.services.retriever_agent import RetrieverAgent

# logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
# logger = logging.getLogger(__name__)

# def main():
#     print("🚀 LangChain ADK - Teacher AI Agent Demo (Retriever Only)\n")

#     class_ = "10th"
#     subject = "Science"
#     query = "Explain photosynthesis in simple terms"
#     # query_without_profile = "Explain Newton's first law of motion"

#     # -------------------------------------------------
#     # Student profile example
#     # -------------------------------------------------
#     student_profile = {
#         "level": "basic",
#         "tone": "friendly",
#         "learning_style": "step-by-step",
#         "response_length": "consise",
#         "include_example": True,  # additional dynamic parameter
#         "language": "English"
#     }

#     # -------------------------------------------------
#     # Initialize retriever agent
#     # -------------------------------------------------
#     retriever_agent = RetrieverAgent()

#     # ✅ Preload once (embedding model only, no LLM call)
#     retriever_agent.load()

#     # print("=" * 60)
#     # print("🔍 Running query WITH student profile")
#     # print("=" * 60)

#     run_query(
#         retriever_agent=retriever_agent,
#         query=query,
#         db_name=class_,
#         collection_name=subject,
#         student_profile=None
#     )

# if __name__ == "__main__":
#     main()




from student_agent import StudentAgent

stagent = StudentAgent()

student_a = {
    "level": "basic",
    "tone": "friendly",
    "learning_style": "step-by-step",
    "response_length": "concise",
    "include_example": False,
    "language": "English",
}

stagent.ask(
    query="Explain photosynthesis in simple terms",
    class_name="10th",
    subject="Science",
    student_profile=None,
)