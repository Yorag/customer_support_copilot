from colorama import Fore, Style
from src.config import RUNTIME_REQUIRED_SETTINGS, validate_required_settings
from src.graph import Workflow


INITIAL_STATE = {
    "emails": [],
    "current_email": {
        "id": "",
        "threadId": "",
        "messageId": "",
        "references": "",
        "sender": "",
        "subject": "",
        "body": "",
    },
    "email_category": "",
    "generated_email": "",
    "rag_queries": [],
    "retrieved_documents": "",
    "writer_messages": [],
    "sendable": False,
    "trials": 0,
}


def main() -> None:
    settings = validate_required_settings(RUNTIME_REQUIRED_SETTINGS)
    config = {"recursion_limit": settings.app.graph_recursion_limit}
    workflow = Workflow()
    app = workflow.app

    print(Fore.GREEN + "Starting workflow..." + Style.RESET_ALL)
    for output in app.stream(INITIAL_STATE, config):
        for key, value in output.items():
            print(Fore.CYAN + f"Finished running: {key}:" + Style.RESET_ALL)


if __name__ == "__main__":
    main()


