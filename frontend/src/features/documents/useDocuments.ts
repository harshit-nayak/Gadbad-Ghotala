import { useNavigate, useParams } from 'react-router-dom';
import { people } from '../../data/people';
import type { DocumentAnalysis, DocumentSource } from '../../domain/types';
import { analyseText } from '../../services/documentService';
import { demoNowIso, uid } from '../../state/clock';
import { useDemo } from '../../state/DemoProvider';

export const documentsUser = `${people.priyaMenon.name}, ${people.priyaMenon.department}`;

export function useDocumentFromRoute() {
  const { documentId } = useParams();
  const { state } = useDemo();
  return state.documents.find((d) => d.id === documentId) ?? null;
}

/** Starts an analysis and opens the progress view. */
export function useStartAnalysis() {
  const { actions } = useDemo();
  const navigate = useNavigate();
  return (input: { name: string; source: DocumentSource; sourceDetail: string; meta: string; text: string }) => {
    const result: DocumentAnalysis = analyseText({
      ...input,
      id: uid('doc'),
      submittedBy: documentsUser,
      at: demoNowIso(),
    });
    actions.addDocument({ ...result, state: 'analysing' });
    actions.logAudit('system', documentsUser, `Submitted ${input.name} for analysis`, 'Document security');
    navigate(`/documents/${result.id}/analysis`);
  };
}
