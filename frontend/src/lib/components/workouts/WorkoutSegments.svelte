<script lang="ts">
	import Caption from '$lib/components/ui/Caption.svelte';
	import Fact from '$lib/components/ui/Fact.svelte';
	import Facts from '$lib/components/ui/Facts.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import Dumbbell from '@lucide/svelte/icons/dumbbell';
	import { DASH, formatDistance, formatDuration, formatPace } from '$lib/utils/format';

	let { segments = [] }: { segments?: Record<string, unknown>[] | null } = $props();

	const overview = $derived((segments ?? []).find((s) => s.kind === 'overview'));
	const strengthSummary = $derived((segments ?? []).find((s) => s.kind === 'strength_summary'));

	const splits = $derived((segments ?? []).filter((s) => s.kind === 'split'));
	const laps = $derived((segments ?? []).filter((s) => s.kind === 'lap'));
	const bestEfforts = $derived((segments ?? []).filter((s) => s.kind === 'best_effort'));

	const views = $derived(
		[
			splits.length > 0 ? { value: 'splits', label: `Splits (${splits.length})` } : null,
			laps.length > 0 ? { value: 'laps', label: `Laps (${laps.length})` } : null,
			bestEfforts.length > 0 ? { value: 'best', label: `Best efforts (${bestEfforts.length})` } : null
		].filter((v): v is { value: string; label: string } => v !== null)
	);

	let activeView = $state('');
	const currentView = $derived(views.find((v) => v.value === activeView)?.value ?? views[0]?.value);

	const displayedItems = $derived(
		currentView === 'laps' ? laps : currentView === 'best' ? bestEfforts : splits
	);
</script>

{#if overview || strengthSummary || views.length > 0}
	<div class="flex flex-col gap-3">
		{#if strengthSummary}
			<div class="rounded-lg border border-border bg-surface-muted/30 p-3.5">
				<div class="flex items-center gap-1.5 pb-2 text-xs font-semibold text-foreground">
					<Dumbbell size={14} class="text-primary" />
					<span>Resumo de Musculação / Séries</span>
				</div>
				<Facts>
					{#if typeof strengthSummary.total_sets === 'number'}
						<Fact label="Total de séries">
							<span class="font-semibold text-foreground">{strengthSummary.total_sets}</span>
						</Fact>
					{/if}
					{#if typeof strengthSummary.work_time_seconds === 'number'}
						<Fact label="Tempo ativo / execução">
							<span>{formatDuration(strengthSummary.work_time_seconds)}</span>
						</Fact>
					{/if}
					{#if typeof strengthSummary.rest_time_seconds === 'number'}
						<Fact label="Tempo de descanso">
							<span>{formatDuration(strengthSummary.rest_time_seconds)}</span>
						</Fact>
					{/if}
					{#if typeof strengthSummary.avg_rest_seconds === 'number'}
						<Fact label="Descanso médio">
							<span>{Math.round(strengthSummary.avg_rest_seconds)}s</span>
						</Fact>
					{/if}
				</Facts>
			</div>
		{/if}

		{#if overview}
			<div class="rounded-lg border border-border bg-surface-muted/30 p-3.5">
				<Facts>
					{#if typeof overview.suffer_score === 'number'}
						<Fact label="Suffer score (Esforço)">
							<span class="font-semibold text-foreground">{Math.round(overview.suffer_score)}</span>
						</Fact>
					{/if}
					{#if typeof overview.perceived_exertion === 'number'}
						<Fact label="Esforço percebido (RPE)">
							<span class="font-semibold text-foreground">{overview.perceived_exertion} / 10</span>
						</Fact>
					{/if}
					{#if typeof overview.average_temp === 'number'}
						<Fact label="Temperatura ambiente">
							<span>{Math.round(overview.average_temp)} °C</span>
						</Fact>
					{/if}
					{#if overview.gear_name}
						<Fact label="Equipamento / Tênis">
							<span class="text-foreground">
								{overview.gear_name}
								{#if typeof overview.gear_distance_meters === 'number'}
									<span class="text-xs text-muted-foreground"
										>({formatDistance(overview.gear_distance_meters)})</span
									>
								{/if}
							</span>
						</Fact>
					{/if}
					{#if overview.description}
						<Fact label="Notas do atleta">
							<span class="text-foreground italic">"{overview.description}"</span>
						</Fact>
					{/if}
				</Facts>
			</div>
		{/if}

		{#if views.length > 0}
			<div class="flex flex-col gap-2.5">
				<div class="flex items-center justify-between gap-3">
					<Caption>Splits & laps</Caption>
					{#if views.length > 1}
						<Segmented
							label="Segment view"
							items={views}
							selected={currentView}
							onselect={(val) => (activeView = val)}
						/>
					{/if}
				</div>

				<div class="overflow-x-auto rounded-lg border border-border">
					<table class="w-full text-left text-xs">
						<thead class="border-b border-border bg-surface-muted/50 text-muted-foreground">
							<tr>
								<th class="px-3 py-2 font-medium">
									{currentView === 'laps' ? 'Lap' : currentView === 'best' ? 'Effort' : 'Split'}
								</th>
								<th class="px-3 py-2 font-medium">Distance</th>
								<th class="px-3 py-2 font-medium">Time</th>
								<th class="px-3 py-2 font-medium">Pace</th>
								<th class="px-3 py-2 font-medium">Avg HR</th>
								{#if currentView === 'laps'}
									<th class="px-3 py-2 font-medium">Cadence</th>
									<th class="px-3 py-2 font-medium">Power</th>
								{:else if currentView === 'splits'}
									<th class="px-3 py-2 font-medium">Elevation</th>
								{/if}
							</tr>
						</thead>
						<tbody class="divide-y divide-border/40 font-mono tabular-nums">
							{#each displayedItems as item, idx}
								{@const dist =
									typeof item.distance_meters === 'number' ? item.distance_meters : null}
								{@const secs =
									typeof item.moving_time_seconds === 'number'
										? item.moving_time_seconds
										: typeof item.elapsed_seconds === 'number'
											? item.elapsed_seconds
											: null}
								{@const pace =
									typeof item.pace_sec_per_km === 'number'
										? item.pace_sec_per_km
										: dist && secs && dist > 0
											? secs / (dist / 1000)
											: null}
								{@const hr =
									typeof item.avg_heart_rate === 'number' ? Math.round(item.avg_heart_rate) : null}
								<tr class="hover:bg-surface-muted/30">
									<td class="px-3 py-1.5 font-sans font-medium text-foreground">
										{item.name
											? String(item.name)
											: `${currentView === 'laps' ? 'Lap' : 'KM'} ${typeof item.index === 'number' ? item.index : idx + 1}`}
									</td>
									<td class="px-3 py-1.5">{formatDistance(dist)}</td>
									<td class="px-3 py-1.5">{formatDuration(secs)}</td>
									<td class="px-3 py-1.5 font-medium text-foreground">{formatPace(pace)}</td>
									<td class="px-3 py-1.5">{hr ? `${hr} bpm` : DASH}</td>
									{#if currentView === 'laps'}
										<td class="px-3 py-1.5">
											{typeof item.avg_cadence === 'number'
												? `${Math.round(item.avg_cadence)} rpm`
												: DASH}
										</td>
										<td class="px-3 py-1.5">
											{typeof item.avg_power === 'number'
												? `${Math.round(item.avg_power)} W`
												: DASH}
										</td>
									{:else if currentView === 'splits'}
										<td class="px-3 py-1.5">
											{typeof item.elevation_difference === 'number'
												? `${item.elevation_difference > 0 ? '+' : ''}${item.elevation_difference} m`
												: DASH}
										</td>
									{/if}
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	</div>
{/if}
