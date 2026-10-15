<script lang="ts">
	import Caption from '$lib/components/ui/Caption.svelte';
	import Segmented from '$lib/components/ui/Segmented.svelte';
	import { DASH, formatDistance, formatDuration, formatPace } from '$lib/utils/format';

	let { segments = [] }: { segments?: Record<string, unknown>[] | null } = $props();

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
						{@const dist = typeof item.distance_meters === 'number' ? item.distance_meters : null}
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
									{typeof item.avg_power === 'number' ? `${Math.round(item.avg_power)} W` : DASH}
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
