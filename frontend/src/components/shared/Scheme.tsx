import {useQuery} from '@tanstack/react-query';
import {GraduationCap, BookOpen, Sprout, Layers3} from 'lucide-react';
import {get} from '../../api/client';
import {Scheme} from '../../api/contracts';
const icons: Record<string, typeof GraduationCap> = {graduation: GraduationCap, book: BookOpen, sprout: Sprout};
export const SchemeIcon = ({icon, size = 22}: {icon?: string; size?: number}) => {const Icon = icons[icon || ''] || Layers3; return <Icon size={size}/>;};
export const useSchemes = () => useQuery<Scheme[]>({queryKey: ['services'], queryFn: async () => (await get('/services')).items, staleTime: 5 * 60 * 1000});
