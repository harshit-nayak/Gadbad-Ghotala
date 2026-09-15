import { useParams } from 'react-router-dom';
import { useDemo } from '../../state/DemoProvider';

export function useIncidentFromRoute() {
  const { incidentId } = useParams();
  const { state } = useDemo();
  return state.incidents.find((i) => i.id === incidentId) ?? null;
}
