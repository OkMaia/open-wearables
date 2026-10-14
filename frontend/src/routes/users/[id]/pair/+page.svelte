<script lang="ts">
	import Unplug from '@lucide/svelte/icons/unplug';
	import Alert from '$lib/components/ui/Alert.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import PairingShell from '$lib/components/pairing/PairingShell.svelte';
	import ProviderChoice from '$lib/components/pairing/ProviderChoice.svelte';
	import type { ActionData, PageData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();
</script>

<svelte:head>
	<title>Conectar dispositivo · Open Wearables</title>
</svelte:head>

<PairingShell title="Conectar dispositivo" lead="Escolha de onde seus dados de saúde serão sincronizados.">
	<div class="flex flex-col gap-4">
		{#if form?.message}
			<Alert>{form.message}</Alert>
		{/if}

		{#if data.providers.length === 0}
			<div class="rounded-xl border border-border bg-surface">
				<EmptyState
					icon={Unplug}
					title="Nenhum dispositivo disponível"
					description="Peça ao administrador para habilitar um provedor de wearables."
				/>
			</div>
		{:else}
			{#each data.providers as provider (provider.provider)}
				<ProviderChoice {provider} returnUrl={data.returnUrl} />
			{/each}
		{/if}
	</div>
</PairingShell>
