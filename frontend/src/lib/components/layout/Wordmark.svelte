<script lang="ts">
	import { cn } from '$lib/utils/cn';

	let { class: className }: { class?: string } = $props();
</script>

<span class={cn('inline-flex items-center justify-center', className)}>
	<img src="/logo.png" alt="Logo" class="h-full w-auto object-contain" />
</span>
