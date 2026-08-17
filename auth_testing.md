# Authentication testing playbook

1. Submit the first signup request; it becomes the initial owner workspace.
2. Submit a second signup request; it remains pending.
3. Log in as the owner and approve the pending account.
4. Log in as the approved user and verify client access is isolated.
5. Set a client limit and verify the user cannot exceed it.
6. Upload financial and ROC source workbooks and verify an import preview is returned.